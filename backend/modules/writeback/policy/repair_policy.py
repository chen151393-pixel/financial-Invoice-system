"""账单补写的可用条件（2026-11-10），详情动作与补写接口共用。"""


def repair_allowed(task, request, gate):
    """(是否可补写, 原因)：仅部分写入且已建 NS 发票记录的任务，并满足写入开关与供应商白名单。"""
    if task["state"] != "partial":
        return False, "只有部分写入的任务需要补写账单"
    if not request or request["state"] != "partial" or not request["ns_record_id"]:
        return False, "缺少已建的 NS 发票记录，不能补写账单"
    allowed, reason = gate.check(task)
    return (True, "可补写账单：只更新账单累计与关联发票，不新建发票记录") if allowed else (False, reason)
