"""NS 来源保存：账户锁覆盖"读取 NS → 保存"全过程，数据库写入在一个短事务内完成，不写 NS。"""

from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.database import check_business_database
from backend.core.errors import ApiError

from ..dao import (
    company_dao,
    customs_declaration_dao,
    lock_dao,
    purchase_order_dao,
    raw_record_dao,
    supplier_dao,
)
from ..mapper.storage_mapper import map_bundle, validate_storage_config
from ..policy.ns_config import parse_config
from . import link_service
from .declaration_service import sync_lock_name
from .ns_reader import PlReader
from .relation_matcher import require_relation_interfaces
from .relation_reader import RelationReader

SYNC_KINDS = ("sub-purchase-orders", "customs-declarations")


class StorageService:
    def __init__(self, ns, engine):
        self.ns, self.engine = ns, engine

    def configuration(self):
        database = check_business_database(self.engine)
        allowed, reason = database["ready"], database["message"]
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

    def account(self):
        account = self.ns.settings.account
        if not account:
            raise ApiError(503, "NS账户未配置")
        return account

    def sync_page(self, kind, read_page):
        """同步页按页读取并保存；分页读取在账户锁内完成。"""
        if kind not in SYNC_KINDS:
            raise ApiError(422, "标准采购订单尚未配置独立存储映射，当前仅支持子采购订单和报关单入库")
        page = None

        def collect():
            nonlocal page
            page = read_page()
            return PlReader(self.ns).collect_records(kind, page["rows"])

        saved = self.save(collect, read_relations=True)
        return {**page, "storage": saved, "message": saved["message"]}

    def save(self, collect, *, read_relations):
        """collect() 在锁内、事务外读取 NS，返回完整的来源数据包。"""
        if self.engine is None:
            raise ApiError(503, "独立MySQL业务库尚未配置")
        config = parse_config(self.ns.settings)
        validate_storage_config(config)
        if read_relations:
            require_relation_interfaces(self.ns.settings)
        account = self.account()
        lock = sync_lock_name(self.engine, account)
        try:
            with self.engine.connect() as connection:
                with connection.begin():
                    acquired = lock_dao.acquire(connection, lock)
                if not acquired:
                    raise ApiError(409, "当前账户已有采购报关保存操作，请完成后再试")
                try:
                    bundle = collect()
                    if read_relations:
                        bundle["relation_evidence"] = RelationReader(self.ns).collect(bundle, match=True)
                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    documents = map_bundle(bundle, config, now)
                    with connection.begin():
                        if not lock_dao.owns(connection, lock):
                            raise ApiError(409, "同步连接已失去占用，未保存，请重新读取")
                        counts = self._write(connection, account, bundle, documents, now)
                finally:
                    # 无论读取、映射或保存是否失败，都释放本次命名锁；断连则丢弃连接。
                    try:
                        if connection.in_transaction():
                            connection.rollback()
                        with connection.begin():
                            lock_dao.release(connection, lock)
                    except SQLAlchemyError:
                        connection.invalidate()
        except SQLAlchemyError:
            raise ApiError(503, "MySQL保存未能确认，请查询本地结果；检查表结构、权限和连接后再重试") from None
        return self._result(bundle, counts)

    def _write(self, connection, account, bundle, documents, now):
        counts = {
            kind: {"created": 0, "updated": 0, "linesCreated": 0, "linesUpdated": 0}
            for kind in ("purchase", "customs")
        }
        customs_ids = customs_declaration_dao.find_ids(
            connection,
            account,
            [document["customs_ns_id"] for document in documents["purchase"] if document["customs_ns_id"]],
        )
        for document in documents["customs"]:
            customs_ids[document["ns_internal_id"]] = self._save_customs(
                connection, account, document, counts, now
            )
        saved_orders = [
            self._save_purchase(connection, account, document, counts, now)
            for document in documents["purchase"]
        ]
        # 先失效改挂或明细已替换的旧关联，再按本次完整读取重建已同步报关单的关联。
        affected = link_service.detach_moved_orders(connection, saved_orders, customs_ids, now)
        order_ids = {order["ns_internal_id"]: order["id"] for order in saved_orders}
        refreshed = set()
        for document in documents["customs"]:
            identity = document["ns_internal_id"]
            members = bundle.get("customs_purchase_membership", {}).get(identity)
            if members is None:
                members = [
                    order["ns_internal_id"] for order in saved_orders if order["customs_ns_id"] == identity
                ]
            evidence = bundle.get("relation_evidence", {}).get(identity)
            link_service.refresh_declaration(
                connection,
                account,
                customs_ids[identity],
                [order_ids[member] for member in members],
                evidence,
                now,
            )
            refreshed.add(customs_ids[identity])
        dependents = (affected | link_service.dependents(connection, saved_orders)) - refreshed
        link_service.mark_dependents(connection, dependents, now)
        link_service.refresh_digests(connection, refreshed | dependents, now)
        return counts

    def _save_customs(self, connection, account, document, counts, now):
        head = dict(document["head"])
        if document["declarant"]:
            head["declarant_company_id"] = company_dao.upsert(connection, account, document["declarant"], now)
        head["raw_record_id"] = raw_record_dao.save(
            connection,
            account,
            document["raw"]["recordType"],
            document["ns_internal_id"],
            document["raw"],
            now,
        )
        for line in document["lines"]:
            line["row"]["company_id"] = (
                company_dao.upsert(connection, account, line["company"], now) if line["company"] else None
            )
        local_id, saved, _ = customs_declaration_dao.save(
            connection, account, {**document, "head": head}, now
        )
        add(counts["customs"], saved)
        return local_id

    def _save_purchase(self, connection, account, document, counts, now):
        head = dict(document["head"])
        head["supplier_id"] = (
            supplier_dao.upsert(connection, account, document["supplier"], now)
            if document["supplier"]
            else None
        )
        head["company_id"] = (
            company_dao.upsert(connection, account, document["company"], now) if document["company"] else None
        )
        head["raw_record_id"] = raw_record_dao.save(
            connection,
            account,
            document["raw"]["recordType"],
            document["ns_internal_id"],
            document["raw"],
            now,
        )
        local_id, saved, line_ids = purchase_order_dao.save(
            connection, account, {**document, "head": head}, now
        )
        add(counts["purchase"], saved)
        return {
            "id": local_id,
            "ns_internal_id": document["ns_internal_id"],
            "customs_ns_id": document["customs_ns_id"],
            "line_ids": line_ids,
        }

    def _result(self, bundle, counts):
        relations = list(bundle.get("relation_evidence", {}).values())
        partial = sum(value["status"] == "partial" for value in relations)
        return {
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
                    bundle["warnings"] + [issue for value in relations for issue in value["issues"]]
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


def add(total, saved):
    for key, value in saved.items():
        total[key] += value
