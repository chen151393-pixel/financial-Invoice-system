"""资料和通知操作前复核冻结依据，防止来源变化后继续发通知。"""

from backend.core.errors import ApiError
from backend.modules.review.public import current_bases

from ..dao import task_dao, task_line_dao

CHANGED = "采购来源或开票依据已变化/未核实，请重新审核后操作"


def _changed(row, bases):
    basis = bases.get(row["purchase_line_id"])
    return not basis or not basis["source_current"] or basis["id"] != row["purchase_basis_id"]


def reason(connection, task_id):
    task = task_dao.get(connection, task_id)
    if task and task["status"] == "superseded":
        return "任务已被新审核版本替代"
    lines = task_line_dao.by_tasks(connection, [task_id])
    bases = current_bases(connection, [row["purchase_line_id"] for row in lines])
    return CHANGED if any(_changed(row, bases) for row in lines) else ""


def changed_task_ids(connection, lines):
    """批量版本：lines 为未被替代任务的任务行，返回来源或依据已变化的任务 ID 集合（只读展示用）。"""
    bases = current_bases(connection, [row["purchase_line_id"] for row in lines])
    return {row["task_id"] for row in lines if _changed(row, bases)}


def require_current(connection, task_id):
    block = reason(connection, task_id)
    if block:
        raise ApiError(409, block)
