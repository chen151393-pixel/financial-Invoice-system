"""发送执行台账查询和条件更新；不决定状态、不提交事务。"""

from sqlalchemy import func, insert, select, update

from ..entity.notification_delivery import deliveries
from ..entity.task_line import task_lines


def get(connection, delivery_id, *, lock=False):
    query = select(deliveries).where(deliveries.c.id == delivery_id)
    row = connection.execute(query.with_for_update() if lock else query).mappings().first()
    return dict(row) if row else None


def by_request(connection, request_id):
    row = (
        connection.execute(select(deliveries).where(deliveries.c.request_id == request_id)).mappings().first()
    )
    return dict(row) if row else None


def history(connection, task_id):
    return [
        dict(row)
        for row in connection.execute(
            select(deliveries).where(deliveries.c.task_id == task_id).order_by(deliveries.c.id.desc())
        ).mappings()
    ]


def overlapping(connection, task_id, statuses):
    own = select(task_lines.c.purchase_line_id).where(task_lines.c.task_id == task_id)
    related = select(task_lines.c.task_id).where(task_lines.c.purchase_line_id.in_(own))
    query = select(deliveries).where(deliveries.c.task_id.in_(related), deliveries.c.status.in_(statuses))
    return [dict(row) for row in connection.execute(query).mappings()]


def insert_delivery(connection, values, now):
    return connection.execute(
        insert(deliveries).values(**values, created_at=now, updated_at=now)
    ).inserted_primary_key[0]


def update_delivery(connection, delivery_id, values, now):
    connection.execute(
        update(deliveries).where(deliveries.c.id == delivery_id).values(**values, updated_at=now)
    )


def count_group(connection, corp_id, chat_id, start, end, statuses):
    return connection.execute(
        select(func.count())
        .select_from(deliveries)
        .where(
            deliveries.c.corp_id == corp_id,
            deliveries.c.chat_id == chat_id,
            deliveries.c.created_at >= start,
            deliveries.c.created_at < end,
            deliveries.c.status.in_(statuses),
        )
    ).scalar_one()
