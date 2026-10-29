"""分配的人工通过条件（数据库设计第 5.3 节）与必须填写说明的情况。

不能通过：发票作废 / 红冲；币种不一致或子采购币种待核实；子采购行没有有效任务行或已停用；
建议生成后子采购行内容变化；发票行已分配数量或金额会超过发票行本身。
超开允许通过，但必须填写说明并标记 exceeds_expected。
"""

from .comparison_policy import AMOUNT_TOLERANCE

STATUS_LABELS = {"proposed": "待审核建议", "confirmed": "已通过", "rejected": "已驳回", "cancelled": "已取消"}
SYSTEM = "system"


def remaining(task_line):
    """子采购行剩余应开（应开为空时剩余也为空）。"""
    quantity = (
        task_line["expected_quantity"] - task_line["received_quantity"]
        if task_line["expected_quantity"] is not None
        else None
    )
    amount = (
        task_line["expected_amount"] - task_line["received_amount"]
        if task_line["expected_amount"] is not None
        else None
    )
    return quantity, amount


def hard_block(invoice, line, task_line):
    """不可绕过的条件；返回原因，可以通过时返回空字符串。"""
    if invoice["status"] != "normal":
        return "发票为作废、红冲或状态未知，不能作为收票依据"
    if invoice.get("detail_status") != "complete":
        return "发票明细未完整或身份待核实，不能确认分配"
    if line is None or not line["active"]:
        return "子采购行已停用或不存在，不能分配"
    if task_line is None:
        return "子采购行没有有效任务行，不在已审核的应开范围内"
    if line.get("basis_reason"):
        return line["basis_reason"]
    if not line["currency"]:
        return f"子采购币种待核实：{line['currency_issue'] or '来源未提供币种'}"
    if invoice["currency"] != line["currency"]:
        return f"发票币种 {invoice['currency']} 与子采购币种 {line['currency']} 不一致，金额无法比较"
    return ""


def capacity_block(item, confirmed_quantity, confirmed_amount, quantity, amount):
    """同一张票不能重复使用：已通过的分配加本次不能超过发票行本身。"""
    if item["quantity"] is not None and confirmed_quantity + quantity > item["quantity"]:
        return "发票行已分配数量将超过发票行本身"
    if item["amount_including_tax"] is not None and confirmed_amount + amount > item["amount_including_tax"]:
        return "发票行已分配金额将超过发票行本身"
    return ""


def exceeds_expected(task_line, quantity, amount):
    expected_quantity, expected_amount = task_line["expected_quantity"], task_line["expected_amount"]
    return (
        expected_quantity is not None and task_line["received_quantity"] + quantity > expected_quantity
    ) or (
        expected_amount is not None
        and task_line["received_amount"] + amount - expected_amount > AMOUNT_TOLERANCE
    )


def note_reasons(checks, exceeds, closes_line):
    """需要填写审核说明的原因列表（为空表示可不填）。

    发票未提供购买方（柠檬云 Excel 不含该列）属于数据缺失：只降低置信度，不要求说明。
    """
    reasons = [
        "发票不含税价格高于申报价" if check["key"] == "price" else f"{check['label']}不一致"
        for check in checks
        if check["result"] != "match"
        and not (check["key"] == "buyer" and check["invoiceValue"] is None)
        # 申报价无法换算、税率未同步时只提示"未校验"，不要求说明
        and not (check["key"] in ("price", "tax") and check["result"] == "missing")
    ]
    if exceeds:
        reasons.append("超过子采购剩余应开（超开）")
    if closes_line:
        reasons.append("确认子采购行已开完（按差异结束）")
    return reasons
