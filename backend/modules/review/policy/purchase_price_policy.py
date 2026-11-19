"""财务采购未税单价：逐行还原未税金额，按采购下单数量加权并折美元。"""

from decimal import ROUND_HALF_UP, Decimal

from backend.modules.source.public import pick_sales_order

CENT = Decimal("0.01")


def purchase_price(customs_row, rows, orders, sales_orders, unit_names=None, bases=None):
    """仅使用当前报关行关联的原始采购行；展示合并行与报关数量不参与除法。"""
    result = {"usd": None, "cny": None, "quantity": None, "unit": "", "note": "", "rate": None}
    if not rows:
        return {**result, "note": "没有行级关联的采购明细，无法计算采购单价"}
    identities = [row["id"] for row in rows if row.get("id") is not None]
    if len(set(identities)) != len(identities):
        return {**result, "note": "关联采购明细重复，无法计算采购单价"}
    quantities = [row.get("quantity") for row in rows]
    if any(quantity is None or quantity <= 0 for quantity in quantities):
        return {**result, "note": "采购下单数量缺失或非正数，无法计算采购单价"}
    result["quantity"] = sum(quantities, Decimal(0))
    result["unit"] = "、".join(
        dict.fromkeys(unit for row in rows if (unit := str(row.get("parent_purchase_unit") or "").strip()))
    )
    candidates = [sales_orders.get(orders[row["purchase_order_id"]].get("sales_order_id")) for row in rows]
    sales, reason = pick_sales_order(customs_row.get("sales_order_no"), candidates)
    if sales is None:
        return {**result, "note": f"{reason}，无法将采购单价折算为 USD"}
    if sales.get("currency") != "USD":
        return {**result, "note": "对应销售单币种不是 USD，无法将采购单价折算为 USD"}
    rate = sales.get("exchange_rate")
    if rate is None or rate <= 0:
        return {**result, "note": "对应销售单汇率缺失或非正数，无法计算采购单价"}
    result["rate"] = rate
    total = Decimal(0)
    for row in rows:
        amount, tax = row.get("amount"), row.get("tax_rate")
        if amount is None or amount <= 0:
            return {**result, "note": "采购含税金额缺失或非正数，无法计算采购单价"}
        if tax is None or not Decimal(0) <= tax <= Decimal(1):
            return {**result, "note": "采购明细税率缺失或无效，无法计算采购未税金额"}
        # NS 金额以分保存；先逐行还原未税金额再相加，不能用平均税率统一除税。
        net = (amount / (Decimal(1) + tax)).quantize(CENT, rounding=ROUND_HALF_UP)
        basis = (bases or {}).get(row.get("id")) or {}
        currency = (
            basis.get("currency")
            if basis.get("allowed")
            else orders[row["purchase_order_id"]].get("currency")
        )
        if currency == "CNY":
            total += net
        elif currency == "USD":
            total += net * rate
        else:
            return {**result, "note": "采购币种待核实或不支持折算为 USD，无法计算采购单价"}
    result["cny"] = total / result["quantity"]
    result["usd"] = result["cny"] / rate
    result["note"] = (
        "关联采购明细逐行按真实税率还原未税金额，合计除以采购下单数量合计，再按对应销售单汇率折算 USD。"
    )
    return result
