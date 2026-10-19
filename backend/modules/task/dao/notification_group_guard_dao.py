"""持久群级守卫，由调用方先持有账本写锁，再锁任务和守卫。"""

from sqlalchemy import insert, select, update

from ..entity.notification_group_guard import notification_group_guards as guards


def get(connection, corp_id, chat_id):
    row = (
        connection.execute(
            select(guards).where(guards.c.corp_id == corp_id, guards.c.chat_id == chat_id).with_for_update()
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def ensure(connection, corp_id, chat_id, now):
    row = get(connection, corp_id, chat_id)
    if row is None:
        connection.execute(
            insert(guards).values(corp_id=corp_id, chat_id=chat_id, created_at=now, updated_at=now)
        )
        row = get(connection, corp_id, chat_id)
    return row


def occupy(connection, corp_id, chat_id, delivery_id, now):
    connection.execute(
        update(guards)
        .where(guards.c.corp_id == corp_id, guards.c.chat_id == chat_id)
        .values(active_delivery_id=delivery_id, updated_at=now)
    )


def release(connection, delivery_id, now):
    connection.execute(
        update(guards)
        .where(guards.c.active_delivery_id == delivery_id)
        .values(active_delivery_id=None, updated_at=now)
    )
