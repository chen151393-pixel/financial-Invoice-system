"""审核状态与能否审核的规则（纯函数）。"""

STATUS_LABELS = {"pending": "待审核", "approved": "审核通过", "unshipped": "未出库"}
CHANGED_WARNING = "来源在上次审核后已变化，旧审核结果不适用于当前内容，请重新审核。"


def status(content_sha256, admission, active_review, basis_required=False):
    """返回 (状态, 是否来源已变化)。admission 为 source 准入规则给出的未出库原因列表。

    - 有效审核的摘要等于当前摘要且审核依据无需复核：审核通过；
    - 未出库（缺真实报关单号或无关联子采购单）：不进入核对，补齐并重新同步后自动进入；
    - 其余：待审核；有旧审核或依据待复核时提示来源已变化。
    """
    changed = bool(active_review) and (active_review["content_sha256"] != content_sha256 or basis_required)
    if active_review and not changed:
        return "approved", False
    if admission:
        return "unshipped", changed
    return "pending", changed


def approve_block_reason(state, content_sha256, requested_sha256, admission_reason=""):
    """不能审核时返回原因，可以审核时返回空字符串。"""
    if not content_sha256 or content_sha256 != requested_sha256:
        return "报关单来源已变化，请刷新后重新核对再审核"
    if state == "unshipped":
        return admission_reason
    return ""
