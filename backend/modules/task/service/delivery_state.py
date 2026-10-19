"""发送状态唯一变更入口，短事务内追加证据事件并维护群守卫。"""

from datetime import UTC, datetime

from backend.core.errors import ApiError

from ..dao import event_dao
from ..dao import notification_delivery_dao as dao
from ..dao import notification_group_guard_dao as guards
from ..policy.delivery_policy import LABELS, TRANSITIONS, writable


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def require_writer(actor):
    if not writable(actor):
        raise ApiError(403, "服务身份只读，不能提交、刷新或核实企微通知")


def owned(connection, task_id, delivery_id, lock=False):
    row = dao.get(connection, int(delivery_id), lock=lock)
    if row is None or row["task_id"] != task_id:
        raise ApiError(404, "本任务中不存在该发送记录")
    return row


def transition(connection, task, row, target, actor, values=None):
    if target not in TRANSITIONS[row["status"]]:
        raise ApiError(409, "发送状态已变化，请刷新后核实")
    at = now()
    dao.update_delivery(connection, row["id"], {**(values or {}), "status": target}, at)
    if target in ("sent", "failed"):
        guards.release(connection, row["id"], at)
    event(connection, task, row["id"], target, actor, at)


def event(connection, task, delivery_id, status, actor, at):
    event_dao.append(
        connection,
        {
            "task_id": task["id"],
            "from_status": task["status"],
            "to_status": task["status"],
            "event_type": "wecom_delivery",
            "reason": LABELS[status],
            "actor": actor,
            "details": {"deliveryId": str(delivery_id), "status": status},
        },
        at,
    )
