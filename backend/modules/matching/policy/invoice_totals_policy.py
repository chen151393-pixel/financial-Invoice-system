"""统计口径：有效分配抵减待匹配金额，失效占用单独列为待复核，不相互抵销。"""

from decimal import Decimal


def invoice_amounts(invoice, confirmed, bases):
    valid, review = Decimal(0), Decimal(0)
    normal = invoice["status"] == "normal"
    for row in confirmed:
        basis = bases.get(row["purchase_line_id"])
        effective = (
            normal
            and invoice["detail_status"] == "complete"
            and row["verification_status"] == "valid"
            and row["effective_invoice"] == invoice["current_version_id"]
            and basis
            and basis["allowed"]
            and row["effective_basis"] == basis["id"]
        )
        if effective:
            valid += row["amount"]
        else:
            review += row["amount"]
    gross = invoice["amount_including_tax"] or Decimal(0)
    pending = max(Decimal(0), gross - valid) if normal else Decimal(0)
    return pending, review
