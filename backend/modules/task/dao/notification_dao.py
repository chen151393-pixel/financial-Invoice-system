"""供应商通知版本：每次保存新增一个版本，人工登记发送时更新最新版本。"""

from sqlalchemy import insert, select, update

from ..entity import notifications


def history(connection, task_id):
    query = (
        select(notifications)
        .where(notifications.c.task_id == task_id)
        .order_by(notifications.c.version.desc())
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def latest(connection, task_id):
    rows = history(connection, task_id)
    return rows[0] if rows else None


def insert_version(connection, values, now):
    connection.execute(
        insert(notifications).values(
            status="draft", channel="manual", created_at=now, updated_at=now, **values
        )
    )


def mark_sent(connection, notification_id, values, now):
    connection.execute(
        update(notifications)
        .where(notifications.c.id == notification_id)
        .values(status="sent", updated_at=now, **values)
    )
