"""任务状态只经此函数修改：检查转换表并写入状态历史（后端规则第 12 节）。"""

from backend.core.errors import ApiError

from ..dao import event_dao, task_dao
from ..policy.task_policy import can_transition


def change_status(connection, task, target, actor, reason, now):
    """调用方须已在同一事务中锁定任务行；task 为锁定后读取的任务。"""
    if not can_transition(task["status"], target):
        raise ApiError(409, "任务状态已变化，请刷新后核对")
    task_dao.set_status(
        connection, task["id"], target, now, completed_at=now if target == "completed" else None
    )
    event_dao.append(
        connection,
        {
            "task_id": task["id"],
            "from_status": task["status"],
            "to_status": target,
            "reason": (reason or "")[:300] or None,
            "actor": actor,
        },
        now,
    )
