"""通知版本只追加；调用方管理任务锁和事务。"""

from sqlalchemy import insert, select, update

from .task_entity import notifications, tasks


def history(connection, task_id):
    return list(
        connection.execute(
            select(notifications)
            .where(notifications.c.task_id == task_id)
            .order_by(notifications.c.revision.desc())
        ).mappings()
    )


def append(connection, values):
    connection.execute(insert(notifications).values(**values))


def mark_recorded(connection, task_id):
    return (
        connection.execute(
            update(tasks)
            .where(tasks.c.id == task_id, tasks.c.status == "notify_pending")
            .values(status="awaiting_invoice")
        ).rowcount
        == 1
    )
