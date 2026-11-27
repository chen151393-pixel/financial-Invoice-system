"""供应商办理范围：只读本模块任务表，不按名称合并身份。"""

from sqlalchemy import or_, select, tuple_

from ..entity import tasks
from .task_dao import BOARD_COLUMNS


def identity(row):
    if not row["ns_account"] or not row["supplier_id"] or not row["company_id"] or not row["currency"]:
        return ("task", row["id"])
    return (row["ns_account"], row["supplier_id"], row["company_id"], row["currency"])


def expand(connection, rows, *, completed=False, all_statuses=False, lock=False, heads_only=False):
    if not rows:
        return []
    keys = {identity(row) for row in rows}
    normal = [key for key in keys if len(key) == 4]
    isolated = [key[1] for key in keys if len(key) == 2]
    clauses = []
    if normal:
        clauses.append(
            tuple_(tasks.c.ns_account, tasks.c.supplier_id, tasks.c.company_id, tasks.c.currency).in_(normal)
        )
    if isolated:
        clauses.append(tasks.c.id.in_(isolated))
    query = select(*(BOARD_COLUMNS if heads_only else (tasks,))).where(or_(*clauses)).order_by(tasks.c.id)
    if not all_statuses:
        query = query.where(
            tasks.c.status == "completed" if completed else tasks.c.status.not_in(("completed", "superseded"))
        )
    if lock:
        query = query.with_for_update()
    return [dict(row) for row in connection.execute(query).mappings()]


def by_anchor(connection, task_id, *, completed=False, lock=False):
    row = connection.execute(select(tasks).where(tasks.c.id == task_id)).mappings().first()
    if not row:
        return []
    active = expand(connection, [dict(row)], completed=completed, lock=lock)
    if active or completed:
        return active
    return expand(connection, [dict(row)], completed=True, lock=lock)
