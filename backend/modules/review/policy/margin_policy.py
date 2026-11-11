"""申报幅度：按同一报关行的 NS 单价与报关单价直接计算。

保留两套数量、单位及原始单价，不按数量比例重算已有单价。仅当报关单价缺失时，
复用 source 的总价 / 报关数量试算。子采购关联用于数量校验及定位销售单汇率，不提供比较价格。
幅度按原币计算；两价按同一销售单汇率折人民币后，沿用固定人民币差额容差。

2026-11-09 用户确认：先比同一报关行的原始口径（NS 数量、单位）与报关口径（报关数量、报关单位）。
单位不同标“单位不一致”，单位相同数量不同标“数量不一致”，两种都不计算申报幅度，按需人工核对处理；
任一口径缺少单位或数量时不做此项比较。两套单位不同时两个单价不可直接相比。
"""

from decimal import ROUND_HALF_UP, Decimal

from backend.modules.source.public import (
    declared_unit_price,
    declared_unit_price_cny,
    pick_sales_order,
    unit_label,
)

from .quantity_policy import quantity_issue

CENT = Decimal("0.01")
DEFAULT_UNIT_PRICE_TOLERANCE_CNY = Decimal("0.10")


# 原始口径与报关口径不一致的状态；与“报关单价低于采购单价”一样需要人工核对
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
):
    """先比原始口径与报关口径，再核对报关数量，价格仍仅取 customs_row 的两个单价字段。"""
    mismatch = caliber_mismatch(customs_row, unit_names)
    if mismatch:
        return mismatch
    issue = quantity_issue(customs_row, purchase_rows, unit_names)
    if issue:
        return unavailable(issue)
    original_price = customs_row["unit_price"]
    if original_price is None:
        return unavailable("采购单价缺失，无法计算申报幅度")
    if original_price <= 0:
        return unavailable("采购单价须大于 0，无法计算申报幅度")
    source_price, _ = declared_unit_price(customs_row)
    if source_price is None:
        return unavailable("报关单价缺失，且报关金额缺失或报关数量无效，无法试算")
    if source_price <= 0:
        return unavailable("报关单价须大于 0，无法计算")
    candidates = [
        sales_orders.get(orders[row["purchase_order_id"]].get("sales_order_id")) for row in purchase_rows
    ]
    sales_order, sales_reason = pick_sales_order(customs_row["sales_order_no"], candidates)
    declared, reason = declared_unit_price_cny(
        source_price, customs_row["currency"], sales_order, sales_reason
    )
    if declared is None:
        return unavailable(f"{reason}，无法计算")
    original, _ = declared_unit_price_cny(original_price, customs_row["currency"], sales_order, sales_reason)
    margin = ((source_price - original_price) / source_price * 100).quantize(CENT, rounding=ROUND_HALF_UP)
    if margin == 0:
        margin = margin.copy_abs()
    # 按未舍入的人民币单价差额判断，避免把刚超出阈值的差额舍入后放行。
    difference = original - declared
    abnormal = difference > tolerance
    note = "报关单价低于采购单价" if abnormal else ""
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
    }
