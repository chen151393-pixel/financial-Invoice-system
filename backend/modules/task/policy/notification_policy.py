"""供应商开票通知：默认正文与可操作判断（人工发送、人工登记，不调用企微）。"""

EDITABLE_STATUSES = ("documents_pending", "notify_pending")
SEND_REASON = "请先保存通知并核对供应商群，提交后仍需群主在企微确认发送。"


def default_message(supplier, company, order_numbers, record_no):
    return (
        f"{supplier}，您好：\n\n本次采购已通过财务审核，请根据合同核对并开具发票。\n"
        f"采购公司：{company or '以合同为准'}\n"
        f"子采购订单：{'、'.join(order_numbers)}\n"
        f"关联报关单：{record_no}\n\n"
        "请核对购销双方信息、品名、数量及金额，并在发票备注中注明子采购订单号。"
        "如已开票，请在群内提供对应发票，谢谢。"
    )


def edit_block(task_status, latest_status):
    if task_status == "superseded":
        return "此任务已被新审核版本替代，仅供追溯。"
    if latest_status == "sent" or task_status not in EDITABLE_STATUSES:
        return "通知已发送或任务已进入收票阶段，通知内容只读。"
    return ""


def record_block(task_status, latest):
    """latest 为最新通知版本（字典）或 None。"""
    block = edit_block(task_status, latest["status"] if latest else None)
    if block:
        return block
    if task_status != "notify_pending":
        return "请先将全部子采购合同保存到共享盘。"
    if not latest or not latest["recipient_name"] or not latest["sender_name"]:
        return "请先填写外部群名称、发送员工并保存通知。"
    return ""
