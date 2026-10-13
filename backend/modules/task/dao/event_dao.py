"""任务状态历史：只追加。"""

from sqlalchemy import insert, select

from ..entity import events


def append(connection, values, now):
    connection.execute(insert(events).values(occurred_at=now, created_at=now, updated_at=now, **values))


def by_task(connection, task_id):
    query = select(events).where(events.c.task_id == task_id).order_by(events.c.occurred_at, events.c.id)
    return [dict(row) for row in connection.execute(query).mappings()]
