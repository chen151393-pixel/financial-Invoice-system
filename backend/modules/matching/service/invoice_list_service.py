"""进项发票按匹配状态筛选（方案 A，见 docs/invoice-match-status-filter.md）。

在同一只读快照中：按列表条件分批读取范围内发票（从新到旧），逐张判定匹配状态并计数；
选中状态的发票 ID 交给 invoice 门面，按原有排序分页。范围超过 SCAN_LIMIT 张时只覆盖较新的发票并提示，
这也是升级为匹配状态投影表（方案 C）的信号。
"""

from collections import defaultdict

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.modules.invoice.public import read_invoice_page, read_invoice_status_scope, read_invoices

from ..dao import allocation_dao
from ..policy.invoice_match_policy import STATUSES, match_status
from ..vo.invoice_list_vo import InvoiceListResult
from .matching_query_service import summary_row, summary_rows

SCAN_LIMIT = 20000


class InvoiceListService:
    def __init__(self, engine):
        self.engine = engine

    def query(self, body):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        try:
            with self.engine.connect() as connection:
                # 计数、筛选与分页使用同一快照，避免扫描期间分配通过或发票换版导致张数与列表不一致
                if connection.dialect.name == "mysql":
                    connection = connection.execution_options(isolation_level="REPEATABLE READ")
                with connection.begin():
                    return self._query(connection, body)
        except SQLAlchemyError:
            raise ApiError(503, "发票列表读取失败，请检查业务数据库及迁移状态") from None

    def _query(self, connection, body):
        filters = body.filters()
        counts = dict.fromkeys(("all", *STATUSES), 0)
        judged, selected = {}, []
        before, capped = None, False
        while True:
            batch = read_invoice_status_scope(connection, filters, before_id=before)
            if not batch:
                break
            allocations = defaultdict(list)
            for row in allocation_dao.by_invoices(connection, [invoice["id"] for invoice in batch]):
                allocations[row["invoice_id"]].append(row)
            for invoice in batch:
                result = match_status(
                    invoice["display_status"], allocations[invoice["id"]], invoice["active_item_count"]
                )
                judged[invoice["id"]] = result
                counts["all"] += 1
                counts[result["status"]] += 1
                if body.matchStatus == result["status"]:
                    selected.append(invoice["id"])
            before = batch[-1]["id"]
            if counts["all"] >= SCAN_LIMIT:
                capped = True
                break
        # “全部”不需要按 ID 限定，直接按原条件分页；其余只在选中的发票内分页
        page = read_invoice_page(
            connection, filters, include_ids=None if body.matchStatus == "all" else selected
        )
        ids = [int(row.id) for row in page.rows]
        known = [invoice_id for invoice_id in ids if invoice_id in judged]
        missing = [invoice_id for invoice_id in ids if invoice_id not in judged]
        rows = {invoice_id: summary_row(invoice_id, judged[invoice_id]) for invoice_id in known}
        if missing:
            invoices = {invoice["id"]: invoice for invoice in read_invoices(connection, missing)}
            for row in summary_rows(connection, missing, invoices):
                rows[int(row["invoiceId"])] = row
        return InvoiceListResult(
            list=page,
            counts=counts,
            summaries=[rows[invoice_id] for invoice_id in ids],
            notice=(
                f"筛选范围超过 {SCAN_LIMIT} 张，匹配状态的张数与筛选只覆盖最新的 {SCAN_LIMIT} 张；请缩小账套或开票日期"
                if capped
                else ""
            ),
        )
