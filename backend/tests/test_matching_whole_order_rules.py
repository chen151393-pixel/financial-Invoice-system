"""整单规则的纯函数：发票少时按明细顺序记账、差额明细识别（2026-10-30）。"""

from decimal import Decimal

from backend.modules.matching.policy.order_group_policy import fit, order_share, share_snapshot, short_lines


def part(line_id, quantity, amount):
    return {
        "invoice_item_id": 1,
        "purchase_line_id": line_id,
        "quantity": Decimal(quantity),
        "purchase_quantity": Decimal(quantity),
        "amount": Decimal(amount),
    }


def item(quantity, amount):
    return {"id": 1, "quantity": Decimal(quantity), "amount_including_tax": Decimal(amount)}


def booked(rows):
    return [(row["quantity"], row["amount"]) for row in rows]


def test_short_invoice_fills_lines_in_order():
    rows = fit([part(1, "10", "100.50"), part(2, "10", "20.00")], item("4", "40.20"))
    assert booked(rows) == [(Decimal(4), Decimal("40.20")), (Decimal(0), Decimal(0))]
    assert [(row["share_quantity"], row["share_amount"]) for row in rows] == [
        (Decimal(10), Decimal("100.50")),
        (Decimal(10), Decimal("20.00")),
    ]
    assert all(row["purchase_quantity"] == row["quantity"] for row in rows)


def test_equal_or_over_invoice_records_full_order():
    parts = [part(1, "10", "100.50"), part(2, "10", "20.00")]
    assert booked(fit(parts, item("20", "120.50"))) == booked(parts)
    assert booked(fit(parts, item("25", "150.00"))) == booked(parts)


def test_missing_invoice_quantity_is_not_capped():
    parts = [part(1, "10", "100.50")]
    rows = fit(parts, {"id": 1, "quantity": None, "amount_including_tax": Decimal("1.00")})
    assert booked(rows) == booked(parts)


def allocation(quantity, amount, share=None):
    return {
        "quantity": Decimal(quantity),
        "amount": Decimal(amount),
        "checks": {"orderShare": share} if share else {},
    }


def test_short_lines_only_from_snapshot():
    full = allocation("10", "100.50", {"quantity": "10", "amount": "100.50"})
    short = allocation("4", "40.20", {"quantity": "10", "amount": "100.50"})
    legacy = allocation("4", "40.20")  # 旧分配没有整单快照，不按差异结束
    assert short_lines([full, short, legacy]) == [short]
    assert order_share(legacy) == (Decimal(4), Decimal("40.20"))
    assert share_snapshot({"share_quantity": Decimal(10), "share_amount": Decimal("100.50")}) == {
        "quantity": "10",
        "amount": "100.50",
    }
