"""整票审核队列的读取编排；沿用逐行比对，不改变审核规则。"""

from backend.modules.invoice.public import read_invoices

from ..dao import allocation_dao, invoice_queue_dao
from ..mapper.allocation_mapper import invoice_side
from ..policy.comparison_policy import text, tier
from ..vo.invoice_queue_vo import InvoiceQueue, InvoiceQueueRow
from ..vo.matching_vo import Capability
from .queue_scope import queue_scope


def invoice_queue(connection, query, render_rows, suppliers):
    groups = invoice_queue_dao.grouped(connection, **queue_scope(connection, query))

    def views(batch):
        ids = [group["invoice_id"] for group in batch]
        invoices = {row["id"]: row for row in read_invoices(connection, ids)}
        proposed = [row for row in allocation_dao.by_invoices(connection, ids) if row["status"] == "proposed"]
        rows_by_invoice = {str(key): [] for key in ids}
        for row in render_rows(connection, proposed):
            rows_by_invoice[row.invoiceId].append(row)
        result = []
        for group in batch:
            own = rows_by_invoice[str(group["invoice_id"])]
            batchable = bool(own) and all(
                row.allocation.tier == "high"
                and row.allocation.confirm.allowed
                and not row.allocation.noteReasons
                for row in own
            )
            result.append(
                InvoiceQueueRow(
                    invoice=invoice_side(invoices[group["invoice_id"]]),
                    proposalCount=len(own),
                    purchaseOrders=list(
                        dict.fromkeys(
                            row.allocation.purchase.orderNo for row in own if row.allocation.purchase
                        )
                    ),
                    confidence=text(group["confidence"]),
                    tier=tier(group["confidence"]),
                    anomalies=list(dict.fromkeys(name for row in own for name in row.anomalies)),
                    batch=Capability(
                        allowed=batchable,
                        reason="全部待审核建议均可直接通过" if batchable else "请进入详情逐行核对",
                    ),
                    batchIds=[row.allocation.id for row in own] if batchable else [],
                )
            )
        return result

    # 异常依赖当前来源与审核能力，按整票分批核对后再筛选，不能截断一张发票。
    evaluated = None
    if query.anomaly != "all":
        evaluated = []
        for start in range(0, len(groups), 100):
            evaluated.extend(views(groups[start : start + 100]))
        evaluated = [row for row in evaluated if bool(row.anomalies) == (query.anomaly == "abnormal")]
        tier_values = [row.tier for row in evaluated]
    else:
        tier_values = [tier(group["confidence"]) for group in groups]
    counts = {"all": len(tier_values), **{key: tier_values.count(key) for key in ("high", "medium", "low")}}
    selected = [
        row
        for row, value in zip(evaluated if evaluated is not None else groups, tier_values)
        if query.tier in ("all", value)
    ]
    total = len(selected)
    pages = max(1, (total + query.pageSize - 1) // query.pageSize)
    page = min(query.page, pages)
    start = (page - 1) * query.pageSize
    page_rows = selected[start : start + query.pageSize]
    return InvoiceQueue(
        rows=page_rows if evaluated is not None else views(page_rows),
        total=total,
        page=page,
        pageSize=query.pageSize,
        pages=pages,
        counts=counts,
        suppliers=suppliers(connection),
    )
