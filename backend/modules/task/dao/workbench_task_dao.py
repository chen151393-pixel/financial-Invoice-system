"""工作台当前任务事实，包含已完成但不包含已被替代版本。"""

from sqlalchemy import select

from ..entity import task_lines, tasks


def read(connection, task_ids=None):
    where = [tasks.c.status != "superseded"]
    if task_ids is not None:
        if not task_ids:
            return [], []
        where.append(tasks.c.id.in_(task_ids))
    heads = [dict(row) for row in connection.execute(select(tasks).where(*where)).mappings()]
    lines = [
        dict(row)
        for row in connection.execute(
            select(
                task_lines.c.task_id,
                task_lines.c.purchase_line_id,
                task_lines.c.expected_amount,
                task_lines.c.received_amount,
                task_lines.c.status,
            )
            .join(tasks, tasks.c.id == task_lines.c.task_id)
            .where(*where)
        ).mappings()
    ]
    return heads, lines
