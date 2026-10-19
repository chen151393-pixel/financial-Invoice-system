"""查询展示分类，不改写来源状态或历史版本；负金额仅识别红字票，不能证明原票被红冲。"""

LABELS = {
    "normal": "正常",
    "red_letter": "红字发票",
    "red_offset": "已被红冲",
    "void": "作废",
    "unknown": "未知",
}
NOTICES = {
    "red_letter": "此票为负数红字发票，请核对备注中的原票信息及历史比对记录。",
    "red_offset": "来源已将此票标记为红冲，请查看历史比对及待复核记录。",
    "void": "此发票已作废，不能作为有效收票依据；已有比对记录请进入比对页查看和复核。",
    "unknown": "票面状态待核实，请先核对来源状态。",
}


def display_status(header):
    status, gross = header["status"], header["amount_including_tax"]
    if status in ("normal", "red_offset") and gross is not None and gross < 0:
        return "red_letter"
    return status
