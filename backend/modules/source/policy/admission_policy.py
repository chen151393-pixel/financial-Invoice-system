"""报关单准入（已出库）规则，2026-10-21 业务确认。

报关单同时满足"有真实报关单号"和"有关联子采购单"才视为已出库，才进入财务核对与待办。
不满足的照常同步保存，补齐后重新同步即自动进入；本规则只决定是否进入流程，不删除或改写来源数据。
"""

NO_DECLARATION_NO = "缺少真实报关单号"
NO_PURCHASE = "没有关联的子采购单"


def admission_issues(declaration_no, order_count):
    """返回未出库原因列表；为空表示已出库。"""
    issues = []
    if not (declaration_no or "").strip():
        issues.append(NO_DECLARATION_NO)
    if not order_count:
        issues.append(NO_PURCHASE)
    return issues


def admission_reason(issues):
    return f"未出库：{'、'.join(issues)}。补齐后重新同步即进入财务核对。" if issues else ""
