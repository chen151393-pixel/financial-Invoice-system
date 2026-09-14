"""按PL完整读取并原子保存；账户级命名锁覆盖读取到提交，不写NS。"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.business_database import check_business_database
from backend.core.errors import ApiError

from . import dao
from .entity import load_tables
from .pl_config import parse_config
from .pl_reader import PlReader
from .storage_mapper import map_bundle, validate_storage_config


class StorageService:
    def __init__(self, ns, engine):
        self.ns, self.engine = ns, engine

    def configuration(self):
        database = check_business_database(self.engine)
        reason = database["message"]
        allowed = database["ready"]
        try:
            validate_storage_config(parse_config(self.ns.settings))
        except ApiError as error:
            allowed, reason = False, error.message
        return {
            "allowed": allowed,
            "reason": "可从NS读取并保存完整单据；重复拉取按来源身份更新" if allowed else reason,
            "localAllowed": database["ready"],
            "database": database,
        }

    def scope(self, owner):
        account = self.ns.settings.account
        if not account:
            raise ApiError(503, "NS账户未配置")
        return hashlib.sha256(owner.encode()).hexdigest(), account

    def sync(self, pl, owner):
        if self.engine is None:
            raise ApiError(503, "独立MySQL业务库尚未配置")
        config = parse_config(self.ns.settings)
        validate_storage_config(config)
        tenant, account = self.scope(owner)
        lock = hashlib.sha256(f"pl-save:{self.engine.url.database}:{tenant}:{account}".encode()).hexdigest()
        counts = {
            kind: {"created": 0, "updated": 0, "linesCreated": 0, "linesUpdated": 0}
            for kind in ("purchase", "customs")
        }
        try:
            with self.engine.connect() as connection:
                with connection.begin():
                    acquired = dao.acquire_sync_lock(connection, lock)
                if not acquired:
                    raise ApiError(409, "当前账户已有采购报关保存操作，请完成后再试")
                try:
                    with connection.begin():
                        tables = load_tables(connection)
                    bundle = PlReader(self.ns).collect(pl, resolve_all_pl=True)
                    documents = map_bundle(bundle, config, tables, tenant, account, pl)
                    with connection.begin():
                        if not dao.owns_sync_lock(connection, lock):
                            raise ApiError(409, "同步连接已失去占用，未保存，请重新读取")
                        customs_ids = {}
                        for kind, head, lines, parent in (
                            (
                                "customs",
                                "customs_declarations",
                                "customs_declaration_lines",
                                "customs_declaration_id",
                            ),
                            ("purchase", "purchase_orders", "purchase_order_lines", "purchase_order_id"),
                        ):
                            for document in documents[kind]:
                                if kind == "purchase":
                                    document["head"]["customs_declaration_id"] = customs_ids.get(
                                        document["customs_id"]
                                    )
                                local_id, saved = dao.save_document(
                                    connection, tables[head], tables[lines], parent, document
                                )
                                if kind == "customs":
                                    customs_ids[document["head"]["ns_internal_id"]] = local_id
                                for key, value in saved.items():
                                    counts[kind][key] += value
                finally:
                    # 无论映射、读取或保存是否失败，都释放本次命名锁；断连则丢弃连接。
                    try:
                        if connection.in_transaction():
                            connection.rollback()
                        with connection.begin():
                            dao.release_sync_lock(connection, lock)
                    except SQLAlchemyError:
                        connection.invalidate()
        except SQLAlchemyError:
            raise ApiError(503, "MySQL保存未能确认，请查询本地结果；检查表结构、权限和连接后再重试") from None
        return {
            "pl": pl,
            "purchase": counts["purchase"],
            "customs": counts["customs"],
            "warnings": bundle["warnings"],
            "savedAt": datetime.now(timezone.utc).isoformat(),
            "message": "完整单据已保存到MySQL"
            if bundle["purchases"]
            else "未找到可保存的采购单，已有本地数据保持不变",
        }

    def query(self, pl, page, owner):
        if self.engine is None:
            raise ApiError(503, "独立MySQL业务库尚未配置")
        tenant, account = self.scope(owner)
        try:
            with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
                with connection.begin():
                    total, records = dao.local_rows(
                        connection, load_tables(connection), tenant, account, pl, page
                    )
        except SQLAlchemyError:
            raise ApiError(503, "本地业务数据查询失败，请检查MySQL表结构和权限") from None
        rows = []
        for record in records:
            group = record["company_identifier"] or f"公司待核实/{record['source']}/{record['id']}"
            values = {
                key: str(value) if value is not None else ""
                for key, value in record.items()
                if key not in ("id", "source", "sort_kind", "company_identifier")
            }
            rows.append(
                {
                    "source": record["source"],
                    "id": str(record["id"]),
                    "group": f"{pl} / {group}",
                    "values": {**values, "pl": pl},
                }
            )
        return {
            "pl": pl,
            "rows": rows,
            "total": total,
            "page": page,
            "hasNext": page * 50 < total,
            "warnings": ["当前为MySQL本地快照；按明细分页，大组可能跨页。不同单位和币种不合计。"],
            "queriedAt": datetime.now(timezone.utc).isoformat(),
        }
