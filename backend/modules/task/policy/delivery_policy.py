"""企微发送状态与能力规则，所有业务判断在服务端。"""

from datetime import UTC, datetime

ACTIVE = ("preparing", "submitting", "pending_confirmation", "unknown")
LABELS = {
    "preparing": "正在准备合同",
    "submitting": "正在提交企微",
    "pending_confirmation": "已提交企微，待群主确认",
    "sent": "企微已确认目标群发送",
    "failed": "发送未完成",
    "unknown": "结果待核实，禁止重复提交",
}
TRANSITIONS = {
    "preparing": {"submitting", "failed"},
    "submitting": {"pending_confirmation", "failed", "unknown"},
    "pending_confirmation": {"sent", "failed"},
    "unknown": {"pending_confirmation", "sent", "failed"},
    "sent": set(),
    "failed": set(),
}
BLOCK_REASON = "本任务或相同子采购行存在未决企微通知，请先查询或核实，不能编辑、人工登记或重复提交。"


def writable(actor):
    return not actor.startswith("service:")


def receipt(rows, chat_id):
    targets = [row for row in rows if row.get("chat_id") == chat_id]
    if len(targets) != 1:
        return None, None, "回执中未找到唯一目标群，保留待确认状态"
    row = targets[0]
    status = row.get("status")
    if type(status) is not int:
        return None, None, "目标群回执状态无法识别"
    if status == 1:
        value = row.get("send_time")
        if type(value) is not int or not 0 < value <= 253402300799:
            return None, None, "目标群成功回执缺少有效发送时间"
        return "sent", datetime.fromtimestamp(value, UTC).replace(tzinfo=None), ""
    if status in (2, 3):
        return "failed", None, "企微明确返回目标群发送失败，请核实客户关系或群发额度"
    return None, None, "目标群尚无可确认的发送成功回执"


def submit_reason(task, latest, binding, settings, blocked, basis=""):
    if basis:
        return basis
    if blocked:
        return BLOCK_REASON
    if not settings or not settings.wecom_send_enabled:
        return "企微发送开关未开启，请由管理员完成渠道验证并启用"
    if not settings.wecom_verified_corp_id:
        return "尚未登记指定群定向发送验收的企业 ID"
    if task["status"] != "notify_pending":
        return "仅资料齐全且待通知的任务可提交企微群发"
    if not latest or latest["status"] != "draft":
        return "请先保存新的通知版本"
    if not binding or not binding["enabled"]:
        return "请先维护启用的供应商默认群"
    return ""
