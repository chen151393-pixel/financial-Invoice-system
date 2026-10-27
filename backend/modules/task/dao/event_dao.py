"""任务状态历史：只追加。"""

from sqlalchemy import func, insert, select

from ..entity import events, tasks


def append(connection, values, now):
    return connection.execute(
        insert(events).values(occurred_at=now, created_at=now, updated_at=now, **values)
    ).inserted_primary_key[0]


def by_task(connection, task_id):
    query = select(events).where(events.c.task_id == task_id).order_by(events.c.occurred_at, events.c.id)
    return [dict(row) for row in connection.execute(query).mappings()]


def by_request(connection, request_id):
    row = connection.execute(select(events).where(events.c.request_id == request_id)).mappings().first()
    return dict(row) if row else None


def first_reached(connection, statuses):
    """当前任务（不含被替代）首次进入各状态的时间：[{task_id, supplier_id, to_status, at}]。"""
    query = (
        select(
            events.c.task_id,
            tasks.c.supplier_id,
            events.c.to_status,
            func.min(events.c.occurred_at).label("at"),
        )
        .join(tasks, tasks.c.id == events.c.task_id)
        .where(tasks.c.status != "superseded", events.c.to_status.in_(statuses))
        .group_by(events.c.task_id, tasks.c.supplier_id, events.c.to_status)
    )
    return [dict(row) for row in connection.execute(query).mappings()]
