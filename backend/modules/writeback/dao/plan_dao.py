"""方案只允许追加。"""

from sqlalchemy import select

from ..entity import plans


def get(connection, plan_id):
    row = connection.execute(select(plans).where(plans.c.id == plan_id)).mappings().first()
    return dict(row) if row else None


def by_request(connection, task_id, request_id):
    row = (
        connection.execute(select(plans).where(plans.c.task_id == task_id, plans.c.request_id == request_id))
        .mappings()
        .first()
    )
    return dict(row) if row else None


def add(connection, values, stamp):
    return connection.execute(
        plans.insert().values(**values, created_at=stamp, updated_at=stamp)
    ).inserted_primary_key[0]
