"""审核状态与能否审核的规则（纯函数）。"""

STATUS_LABELS = {"pending": "待审核", "approved": "审核通过", "blocked": "不可审核"}
CHANGED_WARNING = "来源在上次审核后已变化，旧审核结果不适用于当前内容，请重新审核。"
NO_PURCHASE_REASON = "报关单没有关联的子采购单，审核后不会产生开票范围；请先同步关联子采购单。"


def status(content_sha256, order_count, active_review):
    """返回 (状态, 是否来源已变化)。

    - 有效审核的摘要等于当前摘要：审核通过；
    - 有有效审核但摘要不同：待审核，并提示来源已变化；
    - 没有关联子采购单：不可审核；
    - 其余：待审核。
    """
    changed = bool(active_review) and active_review["content_sha256"] != content_sha256
    if active_review and not changed:
        return "approved", False
    if not order_count:
        return "blocked", changed
    return "pending", changed


def approve_block_reason(state, content_sha256, requested_sha256):
    """不能审核时返回原因，可以审核时返回空字符串。"""
    if not content_sha256 or content_sha256 != requested_sha256:
        return "报关单来源已变化，请刷新后重新核对再审核"
    if state == "blocked":
        return NO_PURCHASE_REASON
    return ""
