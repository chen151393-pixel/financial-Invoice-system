"""供应商开票通知：保存版本、登记人工发送；不调用企微，不以人工登记冒充渠道回执。"""

from datetime import UTC, datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import notification_dao, supplier_group_dao, task_dao
from ..policy.notification_policy import edit_block, record_block
from .basis_guard import require_current
from .task_status_service import change_status


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class NotificationService:
    def __init__(self, engine, tasks):
        self.engine, self.tasks = engine, tasks

    def _write(self, task_id, actor, action):
        if actor.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能保存或登记通知")
        try:
            with transaction(self.engine) as connection:
                require_current(connection, task_id)
                task = task_dao.get(connection, task_id, lock=True)
                if task is None:
                    raise ApiError(404, "开票任务不存在")
                action(connection, task, notification_dao.latest(connection, task_id), _now())
        except SQLAlchemyError:
            raise ApiError(409, "通知未能保存，请刷新核实最新版本后操作") from None
        return self.tasks.detail(task_id)

    def save_draft(self, task_id, body, actor):
        def action(connection, task, latest, now):
            block = edit_block(task["status"], latest["status"] if latest else None)
            if block:
                raise ApiError(409, block)
            if body.revision != (latest["version"] if latest else 0):
                raise ApiError(409, "通知已被修改，请刷新页面后核对最新内容")
            if not body.message:
                raise ApiError(400, "通知内容不能为空")
            group = (
                supplier_group_dao.by_supplier(connection, task["supplier_id"])
                if task["supplier_id"]
                else None
            )
            # 群名与默认群一致时记录群 ID，供以后接入企微自动发送；手填的其他群只记录名称。
            chat_id = (
                group["chat_id"]
                if group and group["enabled"] and group["group_name"] == body.groupName
                else None
            )
            notification_dao.insert_version(
                connection,
                {
                    "task_id": task["id"],
                    "version": body.revision + 1,
                    "chat_id": chat_id,
                    "recipient_name": body.groupName or None,
                    "sender_name": body.employee or None,
                    "content": body.message,
                    "created_by": actor,
                },
                now,
            )

        return self._write(task_id, actor, action)

    def record(self, task_id, body, actor):
        sent_at = body.sentAt.astimezone(UTC).replace(tzinfo=None) if body.sentAt.tzinfo else None

        def action(connection, task, latest, now):
            if latest and latest["status"] == "sent":
                # 相同登记请求的网络重试返回原结果，不产生第二条记录；其他修改一律拒绝。
                same = (
                    body.revision == latest["version"]
                    and body.confirmed
                    and sent_at == latest["sent_at"]
                    and body.note.strip() == latest["note"]
                )
                if same:
                    return
                raise ApiError(409, "已登记发送，请刷新查看原记录，不可重复登记")
            block = record_block(task["status"], latest)
            if block:
                raise ApiError(409, block)
            if body.revision != latest["version"]:
                raise ApiError(409, "通知已被修改，请刷新页面后核对最新内容")
            if not body.confirmed or not body.note.strip():
                raise ApiError(400, "请确认已在企微发送并填写登记说明")
            if sent_at is None or not task["created_at"] <= sent_at <= now:
                raise ApiError(400, "发送时间须带时区，且介于任务生成时间和当前时间之间")
            notification_dao.mark_sent(
                connection,
                latest["id"],
                {"sent_by": actor, "sent_at": sent_at, "note": body.note.strip()},
                now,
            )
            change_status(connection, task, "awaiting_invoice", actor, body.note.strip(), now)

        return self._write(task_id, actor, action)
