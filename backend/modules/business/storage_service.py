"""按PL完整读取并原子保存；账户级命名锁覆盖读取到提交，不写NS。"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.business_database import check_business_database
from backend.core.errors import ApiError

from . import dao, relation_dao
from .entity import load_tables
from .pl_config import parse_config
from .pl_reader import PlReader
from .related_purchase_policy import prepare_related_documents
from .relation_entity import RELATION_TABLE
from .relation_matcher import require_relation_interfaces
from .relation_reader import RelationReader
from .relation_storage_mapper import relation_evidence, relation_values
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
            require_relation_interfaces(self.ns.settings)
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
        def collect():
            reader = PlReader(self.ns)
            bundle = reader.collect(pl, resolve_all_pl=True, discover_customs=True)
            reader.complete_customs_purchases(bundle)
            reader.resolve_pl_names(bundle)
            return bundle

        return self._save(owner, collect, pl, read_relations=True)

    def sync_page(self, kind, read_page, owner):
        """公开保存用例；分页读取在账户锁内完成，与旧PL保存共享事务及去重规则。"""
        if kind not in ("sub-purchase-orders", "customs-declarations"):
            raise ApiError(422, "标准采购订单尚未配置独立存储映射，当前仅支持子采购订单和报关单入库")
        page = None

        def collect():
            nonlocal page
            page = read_page()
            return PlReader(self.ns).collect_records(kind, page["rows"])

        saved = self._save(owner, collect, None, read_relations=True)
        return {**page, "storage": saved, "message": saved["message"]}

    def save_related_snapshot(self, bundle, owner):
        """服务器内部导入完整来源快照；不提供接受浏览器上传原文的接口。"""
        return self._save(owner, lambda: bundle, None, include_parents=True)

    def _save(self, owner, collect, pl, *, include_parents=False, read_relations=False):
        if self.engine is None:
            raise ApiError(503, "独立MySQL业务库尚未配置")
        config = parse_config(self.ns.settings)
        validate_storage_config(config)
        if read_relations:
            require_relation_interfaces(self.ns.settings)
        tenant, account = self.scope(owner)
        lock = hashlib.sha256(f"pl-save:{self.engine.url.database}:{tenant}:{account}".encode()).hexdigest()
        counts = {
            kind: {"created": 0, "updated": 0, "linesCreated": 0, "linesUpdated": 0}
            for kind in (("parent", "purchase", "customs") if include_parents else ("purchase", "customs"))
        }
        try:
            with self.engine.connect() as connection:
                with connection.begin():
                    acquired = dao.acquire_sync_lock(connection, lock)
                if not acquired:
                    raise ApiError(409, "当前账户已有采购报关保存操作，请完成后再试")
                try:
                    with connection.begin():
                        tables = load_tables(
                            connection, include_parents=include_parents, include_relations=True
                        )
                    bundle = collect()
                    if read_relations:
                        bundle["relation_evidence"] = RelationReader(self.ns).collect(bundle, match=True)
                        bundle["warnings"].extend(
                            message
                            for evidence in bundle["relation_evidence"].values()
                            for message in evidence["issues"]
                        )
                    documents = (
                        prepare_related_documents(bundle, config, tables, tenant, account)
                        if include_parents
                        else map_bundle(
                            bundle, config, tables, tenant, account, None if read_relations else pl
                        )
                    )
                    with connection.begin():
                        if not dao.owns_sync_lock(connection, lock):
                            raise ApiError(409, "同步连接已失去占用，未保存，请重新读取")
                        self._invalidate_previous_relations(connection, tables, documents, tenant, account)
                        customs_ids = {}
                        parent_ids, parent_line_ids = {}, {}
                        for document in documents.get("parent", []):
                            local_id, saved = dao.save_document(
                                connection,
                                tables["parent_purchase_orders"],
                                tables["parent_purchase_order_lines"],
                                "parent_purchase_order_id",
                                document,
                            )
                            source_id = document["head"]["ns_internal_id"]
                            parent_ids[source_id] = local_id
                            parent_line_ids[source_id] = dao.document_line_ids(
                                connection,
                                tables["parent_purchase_order_lines"],
                                tenant,
                                "parent_purchase_order_id",
                                local_id,
                            )
                            for key, value in saved.items():
                                counts["parent"][key] += value
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
                                    if include_parents:
                                        source_id = document["parent_source_id"]
                                        document["head"]["parent_purchase_order_id"] = parent_ids.get(
                                            source_id
                                        )
                                        for line in document["lines"]:
                                            key = document["parent_line_keys"][line["source_line_key"]]
                                            line["parent_purchase_order_id"] = parent_ids.get(source_id)
                                            line["parent_purchase_order_line_id"] = (
                                                parent_line_ids[source_id][key] if source_id else None
                                            )
                                local_id, saved = dao.save_document(
                                    connection, tables[head], tables[lines], parent, document
                                )
                                if kind == "customs":
                                    source_id = document["head"]["ns_internal_id"]
                                    customs_ids[source_id] = local_id
                                    relation_dao.save_result(
                                        connection,
                                        tables[RELATION_TABLE],
                                        relation_values(
                                            {**document["head"], "id": local_id},
                                            bundle.get("relation_evidence", {}).get(source_id),
                                        ),
                                    )
                                for key, value in saved.items():
                                    counts[kind][key] += value
                        for source_id, purchase_ids in bundle.get("customs_purchase_membership", {}).items():
                            dao.clear_missing_customs_links(
                                connection,
                                tables["purchase_orders"],
                                tenant,
                                account,
                                customs_ids[source_id],
                                purchase_ids,
                            )
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
        relations = list(bundle.get("relation_evidence", {}).values())
        partial = sum(value["status"] == "partial" for value in relations)
        return {
            "pl": pl,
            **({"parent": counts["parent"]} if include_parents else {}),
            "purchase": counts["purchase"],
            "customs": counts["customs"],
            "relations": {
                "declarations": len(relations),
                "collected": len(relations) - partial,
                "partial": partial,
                "matched": sum(value["status"] == "matched" for value in relations),
                "rawLines": sum(len(value["rawLines"]) for value in relations),
                "packingLines": sum(len(value["packingLines"]) for value in relations),
                "purchaseLinks": sum(len(value["purchaseLinks"]) for value in relations),
            },
            "warnings": list(
                dict.fromkeys(
                    bundle["warnings"]
                    + [
                        warning
                        for group in documents.values()
                        for document in group
                        for warning in document.get("warnings", [])
                    ]
                )
            ),
            "savedAt": datetime.now(timezone.utc).isoformat(),
            "message": (
                "单据及关联结果已保存到MySQL；部分来源存在待核实项"
                if partial
                else "单据、来源依据及逐行关联结果已保存到MySQL"
            )
            if bundle["purchases"] or bundle["customs"]
            else "本页没有可保存的单据，已有本地数据保持不变",
        }

    def _invalidate_previous_relations(self, connection, tables, documents, tenant, account):
        purchase_ids = [document["head"]["ns_internal_id"] for document in documents["purchase"]]
        if not purchase_ids:
            return
        refreshed = [document["head"]["ns_internal_id"] for document in documents["customs"]]
        heads = dao.previous_customs_dependencies(
            connection, tables, tenant, account, purchase_ids, refreshed
        )
        results = {
            row["customs_declaration_id"]: row
            for row in relation_dao.read_results(connection, tables, tenant, [head["id"] for head in heads])
        }
        for head in heads:
            row = results.get(head["id"])
            if row is None:
                continue
            evidence = relation_evidence(row, head["ns_internal_id"])
            # 本地定位也使用 Packing 依据；无 v3 的旧依据同样必须随子单更新失效。
            evidence = {key: value for key, value in evidence.items() if key != "comparison"}
            evidence.update(status="partial", mode="dependency_changed")
            evidence["issues"] = [*evidence.get("issues", []), "关联子采购已更新，请重新完整同步本报关单。"]
            relation_dao.save_result(connection, tables[RELATION_TABLE], relation_values(head, evidence))

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
