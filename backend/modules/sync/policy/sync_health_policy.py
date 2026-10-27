"""近 N 天同步情况：把各类运行记录的状态归为 成功 / 部分成功 / 失败 / 执行中，并按天汇总（纯函数）。"""

# 各运行记录状态 → 结果；未列出的（排队、已拆分）不算一次执行
NS_OUTCOMES = {
    "completed": "success",
    "partial": "partial",
    "interrupted": "partial",
    "unknown": "partial",
    "failed": "failed",
    "running": "running",
}
BATCH_OUTCOMES = {
    "completed": "success",
    "partial": "partial",
    "unknown": "partial",
    "failed": "failed",
    "queued": "running",
    "discovering": "running",
    "running": "running",
}
MANUAL_OUTCOMES = {"completed": "success", "failed": "failed", "running": "running"}

# 行：NS 报关单、NS 子采购、柠檬云发票
ROWS = (
    ("ns-customs", "NS 报关单"),
    ("ns-purchase", "NS 子采购"),
    ("lemon", "柠檬云发票"),
)
NS_KINDS = {"customs-declarations": "ns-customs", "sub-purchase-orders": "ns-purchase"}
BATCH_SOURCES = {"ns_customs": "ns-customs", "ns_purchase": "ns-purchase", "lemon_invoice": "lemon"}
LABELS = {
    "success": "全部成功",
    "partial": "部分成功",
    "failed": "失败",
    "running": "执行中",
    "none": "未执行",
}


def day_status(outcomes):
    """一天内多次执行的汇总：全部成功为成功，全部失败为失败，成败混合或有部分成功为部分成功。"""
    finished = [item for item in outcomes if item != "running"]
    if not outcomes:
        return "none"
    if not finished:
        return "running"
    if all(item == "success" for item in finished):
        return "success"
    if all(item == "failed" for item in finished):
        return "failed"
    return "partial"
