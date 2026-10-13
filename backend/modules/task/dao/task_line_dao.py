"""任务行：新增、有效行查询、替代。"""

from sqlalchemy import insert, select, update

from ..entity import task_lines


def insert_lines(connection, rows, now):
    if rows:
        connection.execute(
            insert(task_lines), [{**row, "created_at": now, "updated_at": now} for row in rows]
        )


def active_purchase_lines(connection, purchase_line_ids):
    """已有有效任务行的子采购行（同一子采购行只生成一次）。"""
    if not purchase_line_ids:
        return set()
    query = select(task_lines.c.purchase_line_id).where(
        task_lines.c.active_purchase_line_id.in_(purchase_line_ids)
    )
    return set(connection.execute(query).scalars())


def by_tasks(connection, task_ids):
    if not task_ids:
        return []
    query = select(task_lines).where(task_lines.c.task_id.in_(task_ids)).order_by(task_lines.c.id)
    return [dict(row) for row in connection.execute(query).mappings()]


def supersede(connection, task_ids, now):
    if task_ids:
        connection.execute(
            update(task_lines)
            .where(task_lines.c.task_id.in_(task_ids))
            .values(status="superseded", updated_at=now)
        )
