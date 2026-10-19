"""工作台当前任务事实，包含已完成但不包含已被替代版本。"""

from sqlalchemy import select

from ..entity import task_lines, tasks


def read(connection):
    heads = [
        dict(row)
        for row in connection.execute(select(tasks).where(tasks.c.status != "superseded")).mappings()
    ]
    lines = [
        dict(row)
        for row in connection.execute(
            select(task_lines)
            .join(tasks, tasks.c.id == task_lines.c.task_id)
            .where(tasks.c.status != "superseded")
        ).mappings()
    ]
    return heads, lines
