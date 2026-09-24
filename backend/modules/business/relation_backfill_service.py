"""为已入库单据补充只读关系证据；不改采购、金额、外键或完整同步时间。"""

import hashlib
import re

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from . import dao, relation_dao
from .entity import load_tables
from .pl_config import parse_config
from .relation_entity import RELATION_TABLE
from .relation_reader import RelationReader
from .relation_storage_mapper import relation_values
from .storage_service import StorageService


class RelationBackfillService:
    def __init__(self, ns, engine):
        self.ns, self.engine = ns, engine

    def targets(self, owner):
        if self.engine is None:
            raise ApiError(503, "独立MySQL业务库尚未配置")
        tenant, account = StorageService(self.ns, self.engine).scope(owner)
        with self.engine.connect() as connection:
            tables = load_tables(connection, include_relations=True)
            return dao.relation_backfill_ids(connection, tables["customs_declarations"], tenant, account)

    def run(self, ids, owner):
        if (
            not isinstance(ids, list)
            or not 1 <= len(ids) <= 20
            or any(
                not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", value) for value in ids
            )
            or len(set(ids)) != len(ids)
        ):
            raise ApiError(422, "补拉须指定1至20个不同的报关内部ID")
        if self.engine is None:
            raise ApiError(503, "独立MySQL业务库尚未配置")
        tenant, account = StorageService(self.ns, self.engine).scope(owner)
        config = parse_config(self.ns.settings)
        lock = hashlib.sha256(f"pl-save:{self.engine.url.database}:{tenant}:{account}".encode()).hexdigest()
        try:
            with self.engine.connect() as connection:
                with connection.begin():
                    acquired = dao.acquire_sync_lock(connection, lock)
                if not acquired:
                    raise ApiError(409, "当前账户已有同步操作，请完成后再试")
                try:
                    with connection.begin():
                        tables = load_tables(connection, include_relations=True)
                        before = dao.relation_backfill_sources(connection, tables, tenant, account, ids)
                    if {row["ns_internal_id"] for row in before["customs"]} != set(ids):
                        raise ApiError(404, "部分报关单未入库、已停用或不属于当前身份账套")
                    bundle = {"customs": [], "purchases": []}
                    for key, spec in (("customs", config.customs), ("purchases", config.purchase)):
                        for row in before[key]:
                            source = row["source_data"]
                            if (
                                not isinstance(source, dict)
                                or source.get("recordId") != row["ns_internal_id"]
                                or source.get("recordType") != spec.type
                                or not isinstance(source.get("record"), dict)
                                or not isinstance(source.get("lines"), list)
                            ):
                                raise ApiError(409, "原单据快照不完整，需重新完整同步")
                            lines = source["lines"]
                            if any(
                                not isinstance(line, dict)
                                or not isinstance(line.get("id"), str)
                                or not isinstance(line.get("record"), dict)
                                for line in lines
                            ):
                                raise ApiError(409, "原单据明细快照不完整，需重新完整同步")
                            bundle[key].append(
                                (
                                    row["ns_internal_id"],
                                    source["record"],
                                    [(line["id"], line["record"]) for line in lines],
                                )
                            )
                    evidence = RelationReader(self.ns).collect(bundle)
                    for row in before["customs"]:
                        value = evidence[row["ns_internal_id"]]
                        # 补拉只证明本次读取到关系；旧采购快照不可当成本次NS重新核实结果。
                        value["status"] = "partial"
                        value["issues"].append(
                            "本次仅补拉关联依据，单据及子采购行沿用原同步快照；需完整同步后核实。"
                        )
                        value["mode"] = "evidence_backfill"
                        value["baseSyncedAt"] = row["synced_at"].isoformat() if row["synced_at"] else None
                    with connection.begin():
                        if not dao.owns_sync_lock(connection, lock):
                            raise ApiError(409, "补拉连接已失去占用，未保存")
                        current = dao.lock_relation_backfill_sources(connection, tables, tenant, account, ids)
                        if current != before:
                            raise ApiError(409, "补拉期间来源快照变化，未保存，请重新读取")
                        for head in before["customs"]:
                            if (
                                relation_dao.save_result(
                                    connection,
                                    tables[RELATION_TABLE],
                                    relation_values(head, evidence[head["ns_internal_id"]]),
                                )
                                != 1
                            ):
                                raise ApiError(409, "补拉目标发生变化，未保存")
                finally:
                    try:
                        if connection.in_transaction():
                            connection.rollback()
                        with connection.begin():
                            dao.release_sync_lock(connection, lock)
                    except SQLAlchemyError:
                        connection.invalidate()
        except SQLAlchemyError:
            raise ApiError(503, "关联依据保存未能确认，请先核实本地记录，不自动重试") from None
        return {
            "account": account,
            "saved": len(evidence),
            "partial": len(evidence),
            "counts": {
                key: sum(len(value[key]) for value in evidence.values())
                for key in ("rawLines", "packingLines", "purchaseLinks", "parentLines")
            },
            "issues": list(dict.fromkeys(issue for value in evidence.values() for issue in value["issues"])),
        }
