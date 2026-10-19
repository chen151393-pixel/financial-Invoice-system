"""发送记录仅暴露可读目标和文件摘要，不暴露快照中的内部路径。"""

from ..policy.delivery_policy import LABELS
from ..vo.capability import Capability
from ..vo.delivery_vo import DeliveryView
from .task_mapper import iso


def view(row):
    snapshot = row["snapshot_json"]
    refresh = row["status"] in ("preparing", "submitting", "pending_confirmation", "unknown")
    reconcile = row["status"] == "unknown"
    return DeliveryView(
        autoPoll=row["status"] == "pending_confirmation",
        id=str(row["id"]),
        revision=snapshot["revision"],
        status=row["status"],
        statusLabel=LABELS[row["status"]],
        corpId=row["corp_id"],
        chatId=row["chat_id"],
        groupName=snapshot["groupName"],
        employee=snapshot["employee"],
        userid=row["sender_userid"],
        message=snapshot["message"],
        files=snapshot["files"],
        createdAt=iso(row["created_at"]),
        submittedAt=iso(row["submitted_at"]),
        sentAt=iso(row["sent_at"]),
        lastCheckedAt=iso(row["last_checked_at"]),
        nextCheckAt=iso(row["next_check_at"]),
        msgid=row["channel_message_id"] or "",
        error=row["error_message"] or "",
        refresh=Capability(allowed=refresh, reason="查询回执或恢复中断执行" if refresh else "执行已结束"),
        reconcile=Capability(
            allowed=reconcile, reason="查询可核实的唯一渠道记录" if reconcile else "当前无需核实"
        ),
    )
