"""通知版本与默认群配置的展示转换。"""

from ..policy.notification_policy import SEND_REASON, default_message, edit_block, record_block
from ..vo.capability import Capability
from ..vo.notification_vo import NotificationDetail, NotificationEvent, NotificationGroup
from .task_mapper import iso


def group(row):
    return NotificationGroup(
        groupName=row["group_name"],
        chatId=row["chat_id"],
        employee=row["owner_name"],
        userid=row["owner_userid"],
        revision=row["version"],
    )


def history(rows, attachments):
    return [
        NotificationEvent(
            channel=row["channel"],
            revision=row["version"],
            actor=row["created_by"],
            at=iso(row["created_at"]),
            groupName=row["recipient_name"] or "",
            employee=row["sender_name"] or "",
            message=row["content"],
            sentAt=iso(row["sent_at"]),
            recordedBy=row["sent_by"] or "",
            note=row["note"] or "",
            attachments=attachments if row["status"] == "sent" else [],
        )
        for row in rows
    ]


def status_label(latest):
    """latest：最新通知版本或 None；详情页与采购任务台共用。"""
    if latest and latest["status"] == "sent":
        return "企微已确认目标群发送" if latest["channel"] == "wecom" else "人工登记已发送"
    return "待通知供应商"


def view(task, summary, rows, attachments, binding, group_reason):
    """rows 为通知版本（新到旧）；binding 为有效的供应商默认群或 None。"""
    latest = rows[0] if rows else None
    default = default_message(summary.supplier, summary.company, summary.orderNumbers, summary.recordNumber)
    edit = edit_block(task["status"], latest["status"] if latest else None)
    record = record_block(task["status"], latest)
    return NotificationDetail(
        supplierGroup=group(binding) if binding else None,
        groupConfigReason=group_reason,
        revision=latest["version"] if latest else 0,
        # 尚未保存通知时带出默认群，已保存的通知保留原内容，不被群配置变化覆盖。
        groupName=(latest["recipient_name"] or "") if latest else (binding["group_name"] if binding else ""),
        employee=(latest["sender_name"] or "") if latest else (binding["owner_name"] if binding else ""),
        message=latest["content"] if latest else default,
        defaultMessage=default,
        statusLabel=status_label(latest),
        edit=Capability(allowed=not edit, reason=edit or "仅保存本任务的群信息和通知内容。"),
        record=Capability(allowed=not record, reason=record or "在企微实际发送后登记。"),
        send=Capability(reason=SEND_REASON),
        history=history(rows, attachments),
    )
