"""申报幅度（2026-10-23 业务确认），纯函数。

申报幅度 =（申报价 − 采购价）÷ 申报价，按报关行金额合计计算：
- 申报价：报关行金额按对应销售单汇率换算为人民币（source 规则）；
- 采购价：该报关行行级关联子采购行的含税金额合计（采购价按含税算）；
- 报关行与子采购行单位不一致、采购币种不是人民币、金额或汇率缺失时不计算，写明原因，不显示 0；
- 只标出负数（采购价高于申报价）。
"""

from decimal import ROUND_HALF_UP, Decimal

from backend.modules.source.public import declared_cny, pick_sales_order, unit_label

CNY = "CNY"
CENT = Decimal("0.01")


def unavailable(note):
    return {"status": "unavailable", "margin": None, "declared": None, "purchase": None, "note": note}


def declared_margin(customs_row, purchase_rows, orders, sales_orders, unit_names=None):
    """customs_row：报关行；purchase_rows：行级关联的子采购行；orders：{子采购单 ID: 单头}；
    sales_orders：{销售单 ID: 单头}。返回 {status, margin, declared, purchase, note}。"""
    if not purchase_rows:
        return unavailable("没有行级关联的子采购行")
    customs_unit = unit_label(customs_row["unit"], unit_names)
    if any(unit_label(row["unit"], unit_names) != customs_unit for row in purchase_rows):
        return unavailable("报关行与子采购行单位不一致，不计算申报幅度")
    currencies = {(orders[row["purchase_order_id"]]["currency"] or "") for row in purchase_rows}
    if currencies != {CNY}:
        return unavailable("采购币种待核实" if "" in currencies else "采购币种不是人民币，不计算申报幅度")
    if any(row["amount"] is None for row in purchase_rows):
        return unavailable("子采购金额缺失，无法计算")
    purchase = sum((row["amount"] for row in purchase_rows), Decimal(0))
    candidates = [
        sales_orders.get(orders[row["purchase_order_id"]].get("sales_order_id")) for row in purchase_rows
    ]
    sales_order, sales_reason = pick_sales_order(customs_row["sales_order_no"], candidates)
    declared, _, reason = declared_cny(
        customs_row["amount"], customs_row["unit_price"], customs_row["currency"], sales_order, sales_reason
    )
    if declared is None:
        return unavailable(f"{reason}，无法计算")
    if declared <= 0:
        return unavailable("申报金额为 0，无法计算")
    margin = ((declared - purchase) / declared * 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "status": "negative" if margin < 0 else "ok",
        "margin": margin,
        "declared": declared.quantize(CENT, rounding=ROUND_HALF_UP),
        "purchase": purchase,
        "note": "采购价高于申报价" if margin < 0 else "",
    }
