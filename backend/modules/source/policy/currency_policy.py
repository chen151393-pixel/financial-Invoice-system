"""子采购单币种规则（2026-10-15 确认）。

| 情况 | 处理 |
| --- | --- |
| 有母采购单 | 继承母采购单币种（purchaseOrder.currency），来源记为 parent_order，汇率保存在母采购单 |
| 子采购独立结算或汇率换算 | NS 子采购单目前没有独立币种、汇率或结算标记字段，暂不适用 |
| 没有母采购单 | 需从合同或其他结算来源人工核实，记为待核实 |
| 来源缺失或冲突 | 记为待核实，保留金额确认限制（发票比对不能通过） |
"""

import re

PARENT = "parent_order"
UNRESOLVED = "unresolved"

# 只接受明确的币种名称，不按内部 ID、地区或“元”等模糊简称推断。
CURRENCY_NAMES = {
    "人民币": "CNY",
    "人民币元": "CNY",
    "美元": "USD",
    "欧元": "EUR",
    "英镑": "GBP",
    "日元": "JPY",
    "港元": "HKD",
    "港币": "HKD",
    "澳大利亚元": "AUD",
    "澳元": "AUD",
    "加拿大元": "CAD",
    "加元": "CAD",
    "新加坡元": "SGD",
    "瑞士法郎": "CHF",
    "新台币": "TWD",
    "CHINESE YUAN": "CNY",
    "US DOLLAR": "USD",
    "EURO": "EUR",
    "BRITISH POUND": "GBP",
    "JAPANESE YEN": "JPY",
    "HONG KONG DOLLAR": "HKD",
    "AUSTRALIAN DOLLAR": "AUD",
    "CANADIAN DOLLAR": "CAD",
    "SINGAPORE DOLLAR": "SGD",
    "SWISS FRANC": "CHF",
    "NEW TAIWAN DOLLAR": "TWD",
}


def currency_code(header):
    """取母单的明确币种代码／名称；保留旧快照代码支持，冲突或未知时待核实。"""
    symbol = str(header.get("currencysymbol") or "").strip().upper()
    name = str(header.get("currencyname") or "").strip().upper()
    named_code = name if name in CURRENCY_NAMES.values() else CURRENCY_NAMES.get(name, "")
    if symbol and (not re.fullmatch(r"[A-Z]{3}", symbol) or (named_code and symbol != named_code)):
        return ""
    return symbol or named_code


def resolve(parent_id, header):
    """返回 (币种, 来源, 待核实原因)；header 为母采购单头（未读取到时为 None）。"""
    if not parent_id:
        return None, UNRESOLVED, "没有母采购单，需从合同或其他结算来源核实币种"
    if header is None:
        return None, UNRESOLVED, "母采购单未读取到，币种待核实"
    code = currency_code(header)
    if not code:
        name = str(header.get("currencyname") or "").strip()
        detail = f"（NS 返回：{name}）" if name else ""
        return None, UNRESOLVED, f"母采购单币种缺失、无法识别或代码与名称冲突{detail}，待核实"
    return code, PARENT, None
