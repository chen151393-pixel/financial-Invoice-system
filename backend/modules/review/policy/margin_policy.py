"""申报幅度使用关联采购未税单价；采购下单数量和销售汇率独立于报关口径校验。"""

from decimal import ROUND_HALF_UP, Decimal

from backend.modules.source.public import (
    declared_unit_price,
    declared_unit_price_cny,
    pick_sales_order,
    unit_label,
)

from .purchase_price_policy import purchase_price
from .quantity_policy import quantity_issue

CENT = Decimal("0.01")
DEFAULT_UNIT_PRICE_TOLERANCE_CNY = Decimal("0.10")


# 母采购对应明细单位与报关单位、或关联子采购报关数量不一致；需要人工核对。
MISMATCH = ("unit_mismatch", "quantity_mismatch")


def unavailable(note, status="unavailable"):
    return {"status": status, "margin": None, "declared": None, "original": None, "note": note}


def declared_margin(
    customs_row,
    purchase_rows,
    orders,
    sales_orders,
    unit_names=None,
    tolerance=DEFAULT_UNIT_PRICE_TOLERANCE_CNY,
    bases=None,
):
    """采购价始终单独返回；数量或单位待核对时，只阻止幅度与自动审核。"""
    purchase = purchase_price(customs_row, purchase_rows, orders, sales_orders, unit_names, bases)

    def blocked(note, status="unavailable"):
        return {**unavailable(note, status), "purchase": purchase, "declared_usd": None}

    issue = quantity_issue(customs_row, purchase_rows, unit_names)
    if issue:
        status, note = issue
        return blocked(note, status)
    if purchase["usd"] is None:
        return blocked(purchase["note"])
    purchase_units = [str(row.get("parent_purchase_unit") or "").strip() for row in purchase_rows]
    declared_unit = unit_label(customs_row.get("declared_unit"), unit_names).strip()
    if not all(purchase_units):
        reason = next(
            (
                row["parent_purchase_unit_issue"]
                for row, unit in zip(purchase_rows, purchase_units)
                if not unit and row.get("parent_purchase_unit_issue")
            ),
            "母采购对应明细的采购单位缺失，请重新同步母采购行依据",
        )
        return blocked(reason)
    if any(unit != declared_unit for unit in purchase_units):
        return blocked("母采购单对应明细的采购单位与报关单位不一致，不计算申报幅度", "unit_mismatch")
    source_price, _ = declared_unit_price(customs_row)
    if source_price is None:
        return blocked("报关单价缺失，且报关金额缺失或报关数量无效，无法试算")
    if source_price <= 0:
        return blocked("报关单价须大于 0，无法计算")
    candidates = [
        sales_orders.get(orders[row["purchase_order_id"]].get("sales_order_id")) for row in purchase_rows
    ]
    sales_order, sales_reason = pick_sales_order(customs_row["sales_order_no"], candidates)
    declared, reason = declared_unit_price_cny(
        source_price, customs_row["currency"], sales_order, sales_reason
    )
    if declared is None:
        return blocked(f"{reason}，无法计算")
    original = purchase["cny"]
    margin = ((declared - original) / declared * 100).quantize(CENT, rounding=ROUND_HALF_UP)
    if margin == 0:
        margin = margin.copy_abs()
    # 按未舍入的人民币单价差额判断，避免把刚超出阈值的差额舍入后放行。
    difference = original - declared
    abnormal = difference > tolerance
    note = "报关单价低于不含税采购单价" if abnormal else ""
    if Decimal(0) < difference <= tolerance:
        difference_text = format(difference, "f")
        if "." in difference_text:
            difference_text = difference_text.rstrip("0").rstrip(".")
        note = f"精度范围内一致（人民币单价差额 {difference_text} 元，容差 {tolerance:.2f} 元）"
    return {
        "status": "negative" if abnormal else "ok",
        "margin": margin,
        "declared": declared,
        "original": original,
        "note": note,
        "purchase": purchase,
        "declared_usd": declared / purchase["rate"],
    }
