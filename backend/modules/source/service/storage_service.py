"""NS 来源保存：账户锁覆盖"读取 NS → 保存"全过程，数据库写入在一个短事务内完成，不写 NS。

读取 NS 期间只持账户锁；提交前才短暂取得全局账本锁，避免长时间读取阻塞财务计算、发票入库等写入。
"""

from contextlib import ExitStack
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core import named_lock, write_lock
from backend.core.database import check_business_database
from backend.core.errors import ApiError
from backend.core.events import EventBus
from backend.integrations.netsuite import request_stats
from backend.integrations.netsuite.read_batch import quiet_progress

from ..dao import (
    company_dao,
    customs_declaration_dao,
    parent_order_dao,
    purchase_order_dao,
    raw_record_dao,
    sales_order_dao,
    supplier_dao,
)
from ..entity import SOURCE_TABLES, sales_orders
from ..mapper.admission_filter import skip_unshipped
from ..mapper.bundle_mapper import map_bundle
from ..mapper.storage_mapper import column_value, map_parent, validate_storage_config
from ..policy.currency_policy import currency_code
from ..policy.currency_policy import resolve as resolve_currency
from ..policy.ns_config import parse_config
from ..policy.optional_field_policy import warnings as missing_field_warnings
from ..policy.unit_price_policy import warnings as unit_price_warnings
from ..public import SourceChanged
from ..vo.storage_result import storage_result
from . import link_service
from .declaration_service import sync_lock_name
from .ns_reader import PlReader
from .parent_order_reader import read_parent_orders
from .parent_reference_service import verify_missing_parents
from .relation_reader import RelationReader
from .sales_order_reader import read_sales_orders

SYNC_KINDS = ("sub-purchase-orders", "customs-declarations")
# 提交时等待账本锁的秒数：此前读取 NS 可能已耗时数分钟，其他持锁写入都是短事务，等待放宽以免白读。
COMMIT_LEDGER_TIMEOUT = 60


class StorageService:
    def __init__(self, ns, engine, events=None):
        self.ns, self.engine = ns, engine
        self.events = events if events is not None else EventBus()

    def configuration(self):
        database = check_business_database(self.engine, SOURCE_TABLES)
        allowed, reason = database["ready"], database["message"]
        try:
            validate_storage_config(parse_config(self.ns.settings))
        except ApiError as error:
            allowed, reason = False, error.message
        return {
            "allowed": allowed,
            "reason": "可保存报关及子采购基础数据；精确追溯缺失会单独提示" if allowed else reason,
            "localAllowed": database["ready"],
            "database": database,
        }

    def account(self):
        account = self.ns.settings.account
        if not account:
            raise ApiError(503, "NS账户未配置")
        return account

    def sync_page(self, kind, read_page, *, progress=None):
        """同步页按页读取并保存；分页读取在账户锁内完成。"""
        if kind not in SYNC_KINDS:
            raise ApiError(422, "标准采购订单尚未配置独立存储映射，当前仅支持子采购订单和报关单入库")
        page = None

        def collect():
            nonlocal page
            page = read_page()
            return PlReader(self.ns, progress).collect_records(kind, page["rows"])

        saved = self.save(collect, read_relations=True, progress=progress)
        return {**page, "storage": saved, "message": saved["message"]}

    def save(self, collect, *, read_relations, progress=None):
        """collect() 在锁内、事务外读取 NS，返回完整的来源数据包。"""
        report = progress or quiet_progress
        report("等待当前账户保存锁")
        if self.engine is None:
            raise ApiError(503, "独立MySQL业务库尚未配置")
        config = parse_config(self.ns.settings)
        validate_storage_config(config)
        account = self.account()
        lock = sync_lock_name(self.engine, account)
        try:
            with self.engine.connect() as connection:
                # 账户锁不等待；账本锁在 commit() 写库前才取得。
                with connection.begin():
                    acquired = named_lock.acquire(connection, lock)
                if not acquired:
                    raise ApiError(409, "当前账户已有采购报关保存操作，请完成后再试")
                try:
                    result = self._save_locked(
                        connection, collect, config, account, lock, read_relations, report
                    )
                finally:
                    # 无论读取、映射或保存是否失败，都释放本次命名锁；断连则丢弃连接。
                    try:
                        if connection.in_transaction():
                            connection.rollback()
                        with connection.begin():
                            named_lock.release(connection, lock)
                    except SQLAlchemyError:
                        connection.invalidate()
        except SQLAlchemyError:
            raise ApiError(503, "MySQL保存未能确认，请查询本地结果；检查表结构、权限和连接后再重试") from None
        return result

    def sync_partial_page(self, kind, read_page, *, progress=None):
        from .partial_sync_service import PartialSyncService

        return PartialSyncService(self).run(kind, read_page, progress)

    def _save_locked(self, connection, collect, config, account, lock, read_relations, report):
        bundle = self.read_bundle(collect, config, read_relations, report)
        return self.commit(connection, bundle, config, account, lock, report)

    def read_bundle(self, collect, config, read_relations, report):
        """事务外读取完整来源数据包；只读 NS，不访问数据库。

        出库准入在补读关联依据之前执行：未出库报关单不拉取入库，也不再为它读取依据。
        """
        bundle = collect()
        skip_unshipped(bundle, config)
        bundle["parent_reference_checks"] = verify_missing_parents(self.ns, bundle, config, report)
        if read_relations:
            report("补齐原始行、Packing 和逐行关联依据")
            bundle["relation_evidence"] = RelationReader(self.ns, report).collect(bundle, match=True)
            report("读取母采购单并核验币种")
            bundle["parent_orders"] = read_parent_orders(self.ns, bundle)
            report("读取销售单汇率")
            bundle["sales_orders"] = read_sales_orders(self.ns, bundle)
        return bundle

    def commit(self, connection, bundle, config, account, lock, report):
        """校验并在一个短事务内写入已读取的数据包；调用方须持有账户锁，账本锁仅在写库期间持有。"""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        report("校验完整来源数据")
        documents = map_bundle(bundle, config, now)
        bundle["warnings"].extend(missing_field_warnings(bundle, config))
        bundle["warnings"].extend(unit_price_warnings(documents, config))
        report("等待账本锁")
        with ExitStack() as stack:
            # 计入批次耗时，便于区分锁等待、NS 读取与写库。
            with request_stats.phase("lock_wait"):
                stack.enter_context(write_lock.hold_ledger(connection, COMMIT_LEDGER_TIMEOUT))
            report("保存到本地数据库，等待整批提交")
            with request_stats.phase("db_write"), connection.begin():
                if not named_lock.owns(connection, lock):
                    raise ApiError(409, "同步连接已失去占用，未保存，请重新读取")
                counts = self._write(connection, account, bundle, documents, now)
        return storage_result(bundle, counts)

    def _write(self, connection, account, bundle, documents, now):
        affected_orders = set()
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
            self._save_purchase(
                connection,
                account,
                document,
                bundle.get("parent_orders", {}),
                counts,
                now,
                affected_orders,
                bundle.get("sales_orders"),
            )
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
        dependents = (
            affected
            | link_service.dependents(connection, saved_orders + [{"id": i} for i in affected_orders])
        ) - refreshed
        link_service.mark_dependents(connection, dependents, now)
        link_service.refresh_digests(connection, refreshed | dependents, now)
        ids = purchase_order_dao.all_line_ids(
            connection, sorted(affected_orders | {r["id"] for r in saved_orders})
        )
        self.events.publish(connection, SourceChanged(account, tuple(ids)))
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

    def _currency(self, connection, account, parent_ns_id, parents, now, affected_orders):
        """子采购单币种取自母采购单；读取不到或无法识别时待核实（policy/currency_policy.py）。"""
        header = parents.get(parent_ns_id) if parent_ns_id else None
        currency, source, issue = resolve_currency(parent_ns_id, header)
        values = {
            "currency": currency,
            "currency_source": source,
            "currency_issue": issue,
            "parent_relation_status": "no_parent" if not parent_ns_id else "linked" if header else "unknown",
            "parent_order_id": None,
            "currency_raw_record_id": None,
        }
        if header is not None:
            raw_id = raw_record_dao.save(connection, account, "purchaseOrder", parent_ns_id, header, now)
            values["currency_raw_record_id"] = raw_id
            values["parent_order_id"] = parent_order_dao.upsert(
                connection,
                account,
                parent_ns_id,
                {
                    **map_parent(header, currency),
                    "raw_record_id": raw_id,
                    "currency_internal_id": str(header.get("currency") or "") or None,
                },
                now,
            )
            affected_orders.update(
                purchase_order_dao.inherited_orders(connection, values["parent_order_id"], values, now)
            )
        return values

    def _sales_order(self, connection, account, document, sales, now):
        """返回销售单本地 ID；没有引用为 None；本次未读取到（读取失败或未补读）返回 False，保留原关联。"""
        ns_id = document.get("sales_order_ns_id")
        if not ns_id:
            return None
        header = (sales or {}).get(ns_id)
        if header is None:
            return False
        return sales_order_dao.upsert(
            connection,
            account,
            ns_id,
            {
                "order_no": str(header.get("tranid") or "")[:150] or None,
                "currency": currency_code(header) or None,
                "currency_name": str(header.get("currencyname") or "")[:100] or None,
                "exchange_rate": column_value(header.get("exchangerate"), sales_orders.c.exchange_rate),
            },
            now,
        )

    def _save_purchase(
        self, connection, account, document, parents, counts, now, affected_orders, sales=None
    ):
        head = dict(document["head"])
        head.update(
            self._currency(connection, account, document["parent_ns_id"], parents, now, affected_orders)
        )
        sales_order_id = self._sales_order(connection, account, document, sales, now)
        if sales_order_id is not False:
            head["sales_order_id"] = sales_order_id
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


def add(total, saved):
    for key, value in saved.items():
        total[key] += value
