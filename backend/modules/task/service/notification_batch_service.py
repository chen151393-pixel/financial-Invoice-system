"""批量登记“线下已通知供应商”：采购在系统外（企微、电话等）通知后，在开票跟进列表勾选任务一次登记。

- 每个任务一个事务，逐个重新校验；不符合条件的跳过并返回原因，不影响其他任务；
- 通知日期由页面选择，按北京时间保存；实际登记时间仍取服务器当前时间；
- 已保存未发送的通知草稿直接登记为已发送；没有草稿时新增一个版本，正文注明系统未发送消息，不臆造通知内容；
- 只登记，不调用企微；与单个任务的人工登记使用同一状态转换与历史记录。
"""

from datetime import UTC, datetime, time, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.modules.identity.public import actor_names

from ..dao import notification_dao, notification_delivery_dao, supplier_group_dao, task_dao
from ..dao.notification_scope_dao import find_scope
from ..policy.delivery_policy import ACTIVE, BLOCK_REASON
from ..policy.notification_policy import OFFLINE_CONTENT, OFFLINE_NOTE, batch_record_block
from ..vo.notification_vo import NotificationBatchResult
from .basis_guard import require_current
from .task_status_service import change_status

SAVE_ERROR = "登记未能保存，请刷新核实后再操作"
BEIJING = timezone(timedelta(hours=8))


def _record(connection, task_id, note, actor, now, notified_on):
    task = task_dao.get(connection, task_id, lock=True)
    if task is None:
        raise ApiError(404, "开票任务不存在")
    require_current(connection, task_id)
    if notification_delivery_dao.overlapping(connection, task_id, ACTIVE):
        raise ApiError(409, BLOCK_REASON)
    latest = notification_dao.latest(connection, task_id)
    scope = find_scope(connection, task_id, latest["id"]) if latest else None
    if scope and len(scope["members"]) > 1:
        raise ApiError(409, "该通知已按供应商合并，请从合并详情统一登记")
    block = batch_record_block(task["status"], latest["status"] if latest else None)
    if block:
        raise ApiError(409, block)
    sent_at = now
    if notified_on is not None:
        created_at = task["created_at"]
        created_on = created_at.replace(tzinfo=UTC).astimezone(BEIJING).date()
        if notified_on < created_on:
            raise ApiError(400, "通知日期不能早于任务生成日期")
        if notified_on != now.replace(tzinfo=UTC).astimezone(BEIJING).date():
            # 历史日期只有日精度；按北京零点存储，同生成日时不早于任务生成时刻。
            day_start = datetime.combine(notified_on, time.min, BEIJING).astimezone(UTC).replace(tzinfo=None)
            sent_at = max(day_start, created_at)
    if latest is None or latest["status"] != "draft":
        group = (
            supplier_group_dao.by_supplier(connection, task["supplier_id"]) if task["supplier_id"] else None
        )
        bound = group if group and group["enabled"] else None
        notification_dao.insert_version(
            connection,
            {
                "task_id": task_id,
                "version": (latest["version"] if latest else 0) + 1,
                "chat_id": bound["chat_id"] if bound else None,
                "recipient_name": bound["group_name"] if bound else None,
                "sender_name": actor_names(connection, [actor])[actor][:100],
                "content": OFFLINE_CONTENT,
                "created_by": actor,
            },
            now,
        )
        latest = notification_dao.latest(connection, task_id)
    notification_dao.mark_sent(
        connection, latest["id"], {"sent_by": actor, "sent_at": sent_at, "note": note}, now
    )
    change_status(connection, task, "awaiting_invoice", actor, note, now)


def validate_batch(body, actor):
    if actor.startswith("service:"):
        raise ApiError(403, "服务身份只读，不能保存或登记通知")
    today = datetime.now(BEIJING).date()
    if body.notifiedOn is not None and body.notifiedOn > today:
        raise ApiError(400, "通知日期不能晚于今天")
    return body.note or OFFLINE_NOTE


def record_batch(engine, body, actor):
    note = validate_batch(body, actor)
    recorded, skipped = [], []
    for task_id in body.taskIds:
        try:
            with transaction(engine, "task") as connection:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                _record(connection, int(task_id), note, actor, now, body.notifiedOn)
        except ApiError as error:
            if error.status not in (400, 404, 409, 422):
                raise  # 数据库不可用等停止后续；已登记的任务不回滚
            skipped.append({"id": task_id, "reason": error.message})
        except SQLAlchemyError:
            skipped.append({"id": task_id, "reason": SAVE_ERROR})
        else:
            recorded.append({"id": task_id})
    return NotificationBatchResult(recorded=recorded, skipped=skipped)
