"""任务状态历史：只追加。"""

from sqlalchemy import func, insert, select

from ..entity import events, tasks


def append(connection, values, now, *, occurred_at=None):
    return connection.execute(
        insert(events).values(occurred_at=occurred_at or now, created_at=now, updated_at=now, **values)
    ).inserted_primary_key[0]


def by_task(connection, task_id):
    return by_tasks(connection, [task_id]).get(task_id, [])


def by_tasks(connection, task_ids):
    if not task_ids:
        return {}
    query = select(events).where(events.c.task_id.in_(task_ids)).order_by(events.c.occurred_at, events.c.id)
    result = {}
    for row in connection.execute(query).mappings():
        result.setdefault(row["task_id"], []).append(dict(row))
    return result


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


def notification_scopes(connection, anchor_task_ids):
    """合并通知的不可变成员证据；沿用事件 JSON，不迁移或删除原通知记录。"""
    if not anchor_task_ids:
        return []
    query = (
        select(events)
        .where(events.c.task_id.in_(anchor_task_ids), events.c.event_type == "supplier_notice_scope")
        .order_by(events.c.id.desc())
    )
    return [dict(row) for row in connection.execute(query).mappings()]
