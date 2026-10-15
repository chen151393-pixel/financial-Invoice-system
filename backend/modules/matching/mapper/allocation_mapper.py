"""分配记录、子采购行上下文 → 响应对象。"""

from datetime import UTC

from ..policy.allocation_policy import STATUS_LABELS, remaining
from ..policy.comparison_policy import text, tier
from ..vo.matching_vo import AllocationView, Check, InvoiceSide, PurchaseSide

INVOICE_STATUS = {"normal": "正常", "red_offset": "已红冲", "void": "作废", "unknown": "未知"}


def iso(value):
    return value.replace(tzinfo=UTC).isoformat() if value else None


def check_views(checks):
    return [Check(**{key: check[key] for key in Check.model_fields}) for check in checks or []]


def purchase_side(purchase_line_id, line, task_line):
    quantity, amount = remaining(task_line) if task_line else (None, None)
    line = line or {}
    return PurchaseSide(
        purchaseLineId=str(purchase_line_id),
        orderNo=line.get("order_no") or "",
        supplier=line.get("supplier_name") or "",
        company=line.get("company_name") or "",
        item=line.get("declaration_name") or line.get("item_name") or "",
        specification=line.get("specification") or "",
        unit=line.get("unit") or "",
        currency=line.get("currency") or "",
        currencyNote=line.get("currency_issue") or ("取自母采购单" if line.get("currency") else ""),
        expectedQuantity=text(task_line["expected_quantity"]) if task_line else None,
        expectedAmount=text(task_line["expected_amount"]) if task_line else None,
        receivedQuantity=text(task_line["received_quantity"]) if task_line else None,
        receivedAmount=text(task_line["received_amount"]) if task_line else None,
        remainingQuantity=text(quantity),
        remainingAmount=text(amount),
        recordNumber=(task_line or {}).get("record_no") or "",
        taskId=str(task_line["task_id"]) if task_line else None,
    )


def allocation_view(row, checks, purchase, capabilities, note_reasons):
    return AllocationView(
        id=str(row["id"]),
        invoiceItemId=str(row["invoice_item_id"]),
        purchaseLineId=str(row["purchase_line_id"]),
        quantity=text(row["quantity"]),
        amount=text(row["amount"]),
        status=row["status"],
        statusLabel=STATUS_LABELS[row["status"]],
        confidence=text(row["confidence"]),
        tier=tier(row["confidence"]),
        checks=check_views(checks),
        exceedsExpected=row["exceeds_expected"],
        closesPurchaseLine=row["closes_purchase_line"],
        proposedBy=row["proposed_by"],
        proposedAt=iso(row["proposed_at"]),
        reviewedBy=row["reviewed_by"],
        reviewedAt=iso(row["reviewed_at"]),
        reviewNote=row["review_note"],
        cancelledBy=row["cancelled_by"],
        cancelledAt=iso(row["cancelled_at"]),
        cancelReason=row["cancel_reason"],
        purchase=purchase,
        noteReasons=note_reasons,
        **capabilities,
    )


def invoice_side(invoice):
    return InvoiceSide(
        id=str(invoice["id"]),
        number=invoice["invoice_no"],
        date=invoice["invoice_date"].isoformat() if invoice["invoice_date"] else None,
        seller=invoice["seller_name"],
        buyer=invoice["buyer_name"],
        status=invoice["status"],
        statusLabel=INVOICE_STATUS[invoice["status"]],
        currency=invoice["currency"],
        gross=text(invoice["amount_including_tax"]),
        remark=invoice["remark"],
    )
