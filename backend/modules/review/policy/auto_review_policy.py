"""申报幅度提醒与「可自动审核通过」预判（纯函数）。

只用于列表提示、概况计数与筛选，不自动写入审核结果；审核仍由财务确认（批量或单张）。
可自动审核通过须同时满足（与上线计划 Q1 的建议一致）：
- 待审核，且来源未在上次审核后变化；
- 子采购行全部有行级关联（没有未关联报关行的子采购行）；
- 全部子采购行含税金额齐全；
- 全部子采购单币种已确定（来源给出或已人工核实）；
- 每条报关行的申报幅度都已算出，采购单价超过报关单价的差额未超出容差。
供应商白名单待业务确认，暂未纳入。
"""


def margin_alert(margins):
    """任一报关行的采购单价超出报关单价容差即提醒。"""
    return any(margin["status"] == "negative" for margin in margins)


def auto_review_reasons(state, changed, unlinked_count, purchase_rows, currencies_known, margins):
    """返回不能自动审核的原因；空列表表示可自动审核通过。"""
    if state != "pending":
        return ["不是待审核状态"]
    reasons = []
    if changed:
        reasons.append("来源在上次审核后已变化，需人工重审")
    if not purchase_rows:
        reasons.append("没有关联的子采购行")
    if unlinked_count:
        reasons.append(f"{unlinked_count} 条子采购行未关联报关行")
    if any(row["amount"] is None for row in purchase_rows):
        reasons.append("子采购含税金额缺失")
    if not currencies_known:
        reasons.append("子采购币种待核实")
    if margin_alert(margins):
        reasons.append("采购单价高于人民币报关单价且超出容差")
    unavailable = [margin["note"] for margin in margins if margin["status"] == "unavailable"]
    if unavailable:
        reasons.append(f"申报幅度无法计算：{unavailable[0]}")
    if not margins:
        reasons.append("没有报关行")
    return reasons
