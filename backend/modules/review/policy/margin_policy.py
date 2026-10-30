"""申报幅度：按同一报关行的 NS 单价与报关单价直接计算。

保留两套数量、单位及原始单价，不按数量比例重算已有单价。仅当报关单价缺失时，
复用 source 的总价 / 报关数量试算。子采购关联仅用于定位销售单汇率，不提供比较价格。
幅度按原币计算；两价按同一销售单汇率折人民币后，沿用固定人民币差额容差。
"""

from decimal import ROUND_HALF_UP, Decimal

from backend.modules.source.public import (
    declared_unit_price,
    declared_unit_price_cny,
    pick_sales_order,
)

CENT = Decimal("0.01")
DEFAULT_UNIT_PRICE_TOLERANCE_CNY = Decimal("0.10")


def unavailable(note):
    return {"status": "unavailable", "margin": None, "declared": None, "original": None, "note": note}


def declared_margin(
    customs_row,
    purchase_rows,
    orders,
    sales_orders,
    tolerance=DEFAULT_UNIT_PRICE_TOLERANCE_CNY,
):
    """价格仅取 customs_row；采购关联只参与销售单汇率定位。"""
    original_price = customs_row["unit_price"]
    if original_price is None:
        return unavailable("报关行单价缺失，无法计算申报幅度")
    if original_price <= 0:
        return unavailable("报关行单价须大于 0，无法计算申报幅度")
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
    note = "报关单价低于报关行单价" if abnormal else ""
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
