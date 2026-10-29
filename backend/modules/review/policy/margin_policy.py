"""申报幅度（2026-10-23 业务确认），纯函数。

申报幅度 =（人民币报关单价 − 采购折算报关单价）÷ 人民币报关单价：
- 报关单价取报关行的申报单价 declared_unit_price（NS custrecord_swc_grossamountzj，与报关数量、
  报关单位配套；2026-10-28 用户确认，不用 custrecord_swc_unitprice），按对应销售单汇率换算为人民币
  （source 规则），不先舍入；NS 未填申报单价时按报关金额 ÷ 报关数量试算（source declared_unit_price），
  页面标注“试算”；
- 采购折算报关单价 = 关联采购行含税总金额 ÷ 总报关数量，不先舍入；
- 比较前要求报关行数量与关联子采购行报关数量合计一致；否则提示数量口径待核对；
- 双方报关单位不一致、采购币种不是人民币、金额数量或申报单价汇率缺失时不计算，不显示 0；
- 采购折算报关单价超过人民币申报单价且差额大于配置容差时才标异常；容差内保留真实幅度。
"""

from decimal import ROUND_HALF_UP, Decimal

from backend.modules.source.public import (
    declared_unit_price,
    declared_unit_price_cny,
    pick_sales_order,
    unit_label,
)

CNY = "CNY"
CENT = Decimal("0.01")
DEFAULT_UNIT_PRICE_TOLERANCE_CNY = Decimal("0.10")


def unavailable(note):
    return {"status": "unavailable", "margin": None, "declared": None, "purchase": None, "note": note}


def declared_margin(
    customs_row,
    purchase_rows,
    orders,
    sales_orders,
    unit_names=None,
    tolerance=DEFAULT_UNIT_PRICE_TOLERANCE_CNY,
):
    """customs_row：报关行；purchase_rows：行级关联的子采购行；orders：{子采购单 ID: 单头}；
    sales_orders：{销售单 ID: 单头}。返回 {status, margin, declared, purchase, note}。"""
    if not purchase_rows:
        return unavailable("没有行级关联的子采购行")
    customs_unit = unit_label(customs_row["declared_unit"], unit_names)
    if not customs_unit or any(not unit_label(row["declared_unit"], unit_names) for row in purchase_rows):
        return unavailable("报关单位缺失，无法计算采购折算报关单价")
    if any(unit_label(row["declared_unit"], unit_names) != customs_unit for row in purchase_rows):
        return unavailable("报关行与子采购行报关单位不一致，不计算申报幅度")
    declared_quantity = customs_row["declared_quantity"]
    if declared_quantity is None:
        return unavailable("数量口径待核对（报关行数量缺失）")
    if declared_quantity <= 0:
        return unavailable("数量口径待核对（报关行数量须大于 0）")
    if any(row["declared_quantity"] is None for row in purchase_rows):
        return unavailable("数量口径待核对（子采购报关数量缺失）")
    if any(row["declared_quantity"] <= 0 for row in purchase_rows):
        return unavailable("数量口径待核对（子采购报关数量须大于 0）")
    quantity = sum((row["declared_quantity"] for row in purchase_rows), Decimal(0))
    # 使用同一报关行下全部关联子采购的报关数量，不用采购数量，也不先舍入或套用价格容差。
    if quantity != declared_quantity:
        return unavailable(
            f"数量口径待核对（报关行 {declared_quantity.normalize():f}，"
            f"子采购报关合计 {quantity.normalize():f}）"
        )
    currencies = {(orders[row["purchase_order_id"]]["currency"] or "") for row in purchase_rows}
    if currencies != {CNY}:
        return unavailable("采购币种待核实" if "" in currencies else "采购币种不是人民币，不计算申报幅度")
    if any(row["amount"] is None for row in purchase_rows):
        return unavailable("采购含税金额缺失，无法计算采购折算报关单价")
    purchase = sum((row["amount"] for row in purchase_rows), Decimal(0)) / quantity
    candidates = [
        sales_orders.get(orders[row["purchase_order_id"]].get("sales_order_id")) for row in purchase_rows
    ]
    sales_order, sales_reason = pick_sales_order(customs_row["sales_order_no"], candidates)
    source_price, _ = declared_unit_price(customs_row)
    declared, reason = declared_unit_price_cny(
        source_price, customs_row["currency"], sales_order, sales_reason
    )
    if declared is None:
        return unavailable(f"{reason}，无法计算")
    if declared <= 0:
        return unavailable("报关单价须大于 0，无法计算")
    margin = ((declared - purchase) / declared * 100).quantize(CENT, rounding=ROUND_HALF_UP)
    if margin == 0:
        margin = margin.copy_abs()
    # 按未舍入的人民币单价差额判断，避免把刚超出阈值的差额舍入后放行。
    difference = purchase - declared
    abnormal = difference > tolerance
    note = "申报单价低于采购折算报关单价" if abnormal else ""
    if Decimal(0) < difference <= tolerance:
        difference_text = format(difference, "f")
        if "." in difference_text:
            difference_text = difference_text.rstrip("0").rstrip(".")
        note = f"精度范围内一致（人民币单价差额 {difference_text} 元，容差 {tolerance:.2f} 元）"
    return {
        "status": "negative" if abnormal else "ok",
        "margin": margin,
        "declared": declared,
        "purchase": purchase,
        "note": note,
    }
