"""报关申报价换算（2026-10-23 业务确认），纯函数。

- 申报价（人民币）= 报关行金额 × 对应销售单汇率；报关行为人民币时不换算；
- 对应销售单：报关行关联子采购单的销售单中，单号与报关行销售订单号一致的；没有一致的且只有一个时取该销售单；
- 汇率不参与报关单内容摘要；缺汇率、币种不一致等无法换算时给出原因，不以 1 或 0 代替。
"""

from decimal import Decimal

from .currency_policy import currency_code

CNY = "CNY"


def pick_sales_order(sales_order_no, candidates):
    """candidates：报关行关联子采购单的销售单行列表（可重复）；返回 (销售单, 原因)。"""
    unique = {row["id"]: row for row in candidates if row}
    matched = [row for row in unique.values() if sales_order_no and row.get("order_no") == sales_order_no]
    if len(matched) == 1:
        return matched[0], ""
    if len(unique) == 1:
        return next(iter(unique.values())), ""
    if not unique:
        return None, "未同步到对应销售单"
    return None, "对应销售单不唯一"


def declared_cny(amount, unit_price, currency, sales_order, sales_reason=""):
    """返回 (人民币申报金额, 人民币申报单价, 原因)；无法换算时金额为 None 并给出原因。"""
    if amount is None:
        return None, None, "报关行金额缺失"
    # 报关明细保留 NS 名称（如 US Dollar），销售单保存代码（USD），先按同一规则识别。
    customs_currency = currency_code({"currencyname": currency})
    if not customs_currency:
        return None, None, "报关行币种待核实"
    if customs_currency == CNY:
        return amount, unit_price, ""
    if sales_order is None:
        return None, None, sales_reason or "未同步到对应销售单"
    sales_currency = currency_code({"currencyname": sales_order.get("currency")})
    if not sales_currency:
        return None, None, "销售单币种待核实"
    if sales_currency != customs_currency:
        return None, None, "报关行币种与销售单币种不一致"
    rate = sales_order.get("exchange_rate")
    if not rate or Decimal(rate) <= 0:
        return None, None, "销售单汇率待同步"
    rate = Decimal(rate)
    return amount * rate, (unit_price * rate if unit_price is not None else None), ""


def declared_unit_price_cny(unit_price, currency, sales_order, sales_reason=""):
    """单价独立换算，不要求报关总金额存在，也不从金额和数量倒算单价。"""
    if unit_price is None:
        return None, "申报单价缺失（重新同步报关单后补齐）"
    converted, _, reason = declared_cny(unit_price, None, currency, sales_order, sales_reason)
    return converted, reason
