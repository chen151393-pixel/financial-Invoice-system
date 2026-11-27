"""合并通知成员从追加式事件恢复；版本、锁和回执均覆盖固定成员，不修改原审核台账。"""

from backend.core.errors import ApiError

from ..dao import notification_dao, supplier_task_dao, task_dao
from ..dao.notification_scope_dao import find_scope as find_scope
from ..policy.notification_policy import EDITABLE_STATUSES
from .basis_guard import reason as basis_reason


def members(connection, task_id, notification_id, *, lock=False):
    scope = find_scope(connection, task_id, notification_id)
    ids = [member["taskId"] for member in scope["members"]] if scope else [task_id]
    return task_dao.by_ids(connection, sorted(ids), lock=lock), scope


def validate(connection, scope):
    if not scope:
        return
    for member in scope["members"]:
        latest = notification_dao.latest(connection, member["taskId"])
        if not latest or latest["id"] != member["notificationId"]:
            raise ApiError(409, "合并通知成员或版本已变化，请重新保存并预览")
        if block := basis_reason(connection, member["taskId"]):
            raise ApiError(409, block)


def validate_current_members(connection, data):
    if not data.get("scope"):
        return
    rows = supplier_task_dao.by_anchor(connection, data["task"]["id"])
    pending = {
        row["id"]
        for row in rows
        if row["status"] in EDITABLE_STATUSES
        and (notification_dao.latest(connection, row["id"]) or {}).get("status") != "sent"
    }
    if pending != {row["id"] for row in data["scopeTasks"]}:
        raise ApiError(409, "待通知任务范围已变化，请返回合并详情重新保存并预览")
