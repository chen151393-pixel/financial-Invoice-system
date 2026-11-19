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


# 报关行原始／报关口径或关联子采购报关数量不一致；需要人工核对
MISMATCH = ("unit_mismatch", "quantity_mismatch")


def unavailable(note, status="unavailable"):
    return {"status": status, "margin": None, "declared": None, "original": None, "note": note}


def _number(value):
    return format(value.normalize(), "f")


def caliber_mismatch(customs_row, unit_names=None):
    """同一报关行原始口径对报关口径；一致或无法比较时返回 None。"""
    original_unit = unit_label(customs_row.get("unit"), unit_names).strip()
    declared_unit = unit_label(customs_row.get("declared_unit"), unit_names).strip()
    if not original_unit or not declared_unit:
        return None
    if original_unit != declared_unit:
        return unavailable(
            f"原始单位“{original_unit}”与报关单位“{declared_unit}”不一致，不计算申报幅度", "unit_mismatch"
        )
    quantity, declared_quantity = customs_row.get("quantity"), customs_row.get("declared_quantity")
    # 数量缺失或非正数交给 quantity_issue 提示“数量口径待核对”
    if quantity is None or declared_quantity is None or quantity <= 0 or declared_quantity <= 0:
        return None
    if quantity == declared_quantity:
        return None
    return unavailable(
        f"原始数量 {_number(quantity)} 与报关数量 {_number(declared_quantity)} 不一致，不计算申报幅度",
        "quantity_mismatch",
    )


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

    mismatch = caliber_mismatch(customs_row, unit_names)
    if mismatch:
        return {**mismatch, "purchase": purchase, "declared_usd": None}
    issue = quantity_issue(customs_row, purchase_rows, unit_names)
    if issue:
        status, note = issue
        return blocked(note, status)
    if purchase["usd"] is None:
        return blocked(purchase["note"])
    purchase_units = [unit_label(row.get("unit"), unit_names).strip() for row in purchase_rows]
    declared_unit = unit_label(customs_row.get("declared_unit"), unit_names).strip()
    if not all(purchase_units):
        return blocked("采购单位缺失，无法比较申报幅度")
    if any(unit != declared_unit for unit in purchase_units):
        return blocked("采购下单单位与报关单位不一致，不计算申报幅度", "unit_mismatch")
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
