"""本地通知版本管理；不调用企微，不以人工记录冒充渠道回执。"""

import json
import time
from datetime import UTC, datetime

from backend.core.errors import ApiError

from . import notification_dao, task_dao
from .task_vo import NotificationDetail, NotificationEvent, TaskCapability


def view(row, history, source_status, source_message, ready):
    orders = json.loads(row["payload"])["orders"]
    default = (
        f"{row['supplier']}，您好：\n\n本次采购已通过财务审核，请根据合同核对并开具发票。\n"
        f"采购公司：{row['company'] or '以合同为准'}\n"
        f"子采购订单：{'、'.join(item['number'] for item in orders)}\n"
        f"关联报关单：{row['record_number']}\n\n"
        "请核对购销双方信息、品名、数量及金额，并在发票备注中注明子采购订单号。"
        "如已开票，请在群内提供对应发票，谢谢。"
    )
    events = [
        NotificationEvent(
            revision=item["revision"],
            actor=item["actor"],
            at=datetime.fromtimestamp(item["created_at"], UTC).isoformat(),
            **json.loads(item["payload"]),
        )
        for item in history
    ]
    latest = events[0] if events else None
    recorded = bool(latest and latest.sentAt)
    block = (
        source_message
        if source_status != "current"
        else ("已人工登记发送，通知快照只读。" if recorded else "")
    )
    record_block = (
        block
        or ("请先将全部子采购合同保存到共享盘。" if not ready else "")
        or (
            "请先填写外部群名称、发送员工并保存通知。"
            if not latest or not latest.groupName or not latest.employee
            else ""
        )
    )
    return NotificationDetail(
        revision=latest.revision if latest else 0,
        groupName=latest.groupName if latest else "",
        employee=latest.employee if latest else "",
        message=latest.message if latest else default,
        defaultMessage=default,
        statusLabel="人工登记已发送" if recorded else "待人工发送",
        edit=TaskCapability(allowed=not block, reason=block or "仅保存本任务的群信息和通知内容。"),
        record=TaskCapability(allowed=not record_block, reason=record_block or "在企微实际发送后登记。"),
        send=TaskCapability(reason="企微自动发送接口尚未接入，请复制通知并由员工在外部群发送合同。"),
        history=events,
    )


def save(connection, row, body, owner, *, record=False):
    """调用前必须锁定当前审核来源、审核头及任务行。"""
    history = notification_dao.history(connection, row["id"])
    latest = history[0] if history else None
    revision = latest["revision"] if latest else 0
    data = json.loads(latest["payload"]) if latest else {}
    # 相同登记请求的网络重试返回原结果，不产生第二条记录；其他修改一律拒绝。
    if record and data.get("sentAt"):
        if (
            body.revision == revision - 1
            and body.confirmed
            and body.sentAt.isoformat() == data["sentAt"]
            and body.note.strip() == data["note"]
        ):
            return
        raise ApiError(409, "已登记发送，请刷新查看原记录，不可重复登记")
    if body.revision != revision:
        raise ApiError(409, "通知已被修改，请刷新页面后核对最新内容")
    if data.get("sentAt") or row["status"] == "awaiting_invoice":
        raise ApiError(409, "已登记发送的通知不能修改")
    if record:
        documents = task_dao.document_rows(connection, row["id"])
        orders = json.loads(row["payload"])["orders"]
        if (
            row["status"] != "notify_pending"
            or not orders
            or {d["order_id"] for d in documents if d["archived_at"]} != {o["id"] for o in orders}
        ):
            raise ApiError(409, "请先将全部子采购合同保存到共享盘")
        if not data.get("groupName") or not data.get("employee"):
            raise ApiError(409, "请先填写外部群名称、发送员工并保存通知")
        if not body.confirmed or not body.note.strip():
            raise ApiError(400, "请确认已在企微发送并填写登记说明")
        if body.sentAt.tzinfo is None or not row["created_at"] <= body.sentAt.timestamp() <= time.time():
            raise ApiError(400, "发送时间须带时区，且介于任务生成时间和当前时间之间")
        data.update(
            sentAt=body.sentAt.isoformat(),
            note=body.note.strip(),
            attachments=[d["filename"] for d in documents],
        )
        if not notification_dao.mark_recorded(connection, row["id"]):
            raise ApiError(409, "任务状态已变化，请刷新后核对")
    else:
        if not body.message.strip():
            raise ApiError(400, "通知内容不能为空")
        data = {"groupName": body.groupName, "employee": body.employee, "message": body.message}
    notification_dao.append(
        connection,
        {
            "task_id": row["id"],
            "revision": revision + 1,
            "actor": owner,
            "created_at": int(time.time()),
            "payload": json.dumps(data, ensure_ascii=False),
        },
    )
