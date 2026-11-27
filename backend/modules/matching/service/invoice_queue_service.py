"""整票审核队列的读取编排；沿用逐行比对，不改变审核规则。"""

from decimal import Decimal

from backend.modules.invoice.public import invoice_display_status, read_invoices

from ..dao import allocation_dao, invoice_queue_dao
from ..mapper.allocation_mapper import invoice_side
from ..policy.comparison_policy import text, tier
from ..vo.invoice_queue_vo import InvoiceQueue, InvoiceQueueRow
from ..vo.matching_vo import Capability
from .queue_scope import queue_scope


def invoice_queue(connection, query, render_rows, suppliers):
    groups = invoice_queue_dao.grouped(connection, **queue_scope(connection, query))
    # 红字、已被红冲、作废、未知等票面不参与比对，只在进项发票中查看
    headers = {
        invoice["id"]: invoice for invoice in read_invoices(connection, [g["invoice_id"] for g in groups])
    }
    groups = [
        group
        for group in groups
        if group["invoice_id"] in headers and invoice_display_status(headers[group["invoice_id"]]) == "normal"
    ]

    cached = {}

    def views(batch):
        missing = [group for group in batch if group["invoice_id"] not in cached]
        if not missing:
            return [cached[group["invoice_id"]] for group in batch]
        ids = [group["invoice_id"] for group in missing]
        invoices = headers
        proposed = [row for row in allocation_dao.by_invoices(connection, ids) if row["status"] == "proposed"]
        rows_by_invoice = {str(key): [] for key in ids}
        for row in render_rows(connection, proposed, invoices=invoices):
            rows_by_invoice[row.invoiceId].append(row)
        result = []
        for group in missing:
            own = rows_by_invoice[str(group["invoice_id"])]
            batchable = bool(own) and all(
                row.allocation.confidence is not None
                and Decimal(row.allocation.confidence) == Decimal(100)
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
                        reason="全部待审核建议置信度为 100%，可批量审核通过"
                        if batchable
                        else "仅 100% 且无需异常说明的发票可批量审核，请进入详情核对",
                    ),
                    batchIds=[row.allocation.id for row in own] if batchable else [],
                )
            )
        cached.update({int(row.invoice.id): row for row in result})
        return [cached[group["invoice_id"]] for group in batch]

    def evaluate(batch):
        rows = []
        for start in range(0, len(batch), 100):
            rows.extend(views(batch[start : start + 100]))
        return rows

    # 可自动审核通过：只有最低置信度为 100% 的发票才可能满足，逐张核对能否批量审核
    automatic = [
        row for row in evaluate([g for g in groups if Decimal(g["confidence"]) == 100]) if row.batch.allowed
    ]
    # 异常依赖当前来源与审核能力，按整票分批核对后再筛选，不能截断一张发票。
    evaluated = None
    if query.view == "auto":
        evaluated = automatic
    elif query.anomaly != "all":
        evaluated = evaluate(groups)
    if evaluated is not None and query.anomaly != "all":
        evaluated = [row for row in evaluated if bool(row.anomalies) == (query.anomaly == "abnormal")]
    if evaluated is not None:
        tier_values = [row.tier for row in evaluated]
    else:
        tier_values = [tier(group["confidence"]) for group in groups]
    counts = {
        "all": len(tier_values),
        **{key: tier_values.count(key) for key in ("high", "medium", "low")},
        # 概况卡：全部待审核发票与可自动审核通过张数，不随置信度分段与当前视图变化
        "pending": len(groups),
        "auto": len(automatic),
    }
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
