"""资料和通知操作前复核冻结依据，防止来源变化后继续发通知。"""

from backend.core.errors import ApiError
from backend.modules.review.public import current_bases

from ..dao import task_dao, task_line_dao


def reason(connection, task_id):
    task = task_dao.get(connection, task_id)
    if task and task["status"] == "superseded":
        return "任务已被新审核版本替代"
    lines = task_line_dao.by_tasks(connection, [task_id])
    bases = current_bases(connection, [row["purchase_line_id"] for row in lines])
    for row in lines:
        basis = bases.get(row["purchase_line_id"])
        if not basis or not basis["source_current"] or basis["id"] != row["purchase_basis_id"]:
            return "采购来源或开票依据已变化/未核实，请重新审核后操作"
    return ""


def require_current(connection, task_id):
    block = reason(connection, task_id)
    if block:
        raise ApiError(409, block)
