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


def currency_code(header):
    """母采购单头中的三位币种代码；无法识别时返回空。"""
    symbol = str(header.get("currencysymbol") or "").strip().upper()
    return symbol if re.fullmatch(r"[A-Z]{3}", symbol) else ""


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
        return None, UNRESOLVED, f"母采购单币种缺失或无法识别为三位代码{detail}，待核实"
    return code, PARENT, None
