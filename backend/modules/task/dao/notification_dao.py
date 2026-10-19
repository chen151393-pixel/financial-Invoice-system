"""供应商通知版本：每次保存新增一个版本，人工登记发送时更新最新版本。"""

from sqlalchemy import func, insert, select, update

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


def latest_sent_by_tasks(connection, task_ids):
    """批量读取最近实际发送；新草稿、失败与待群主确认不覆盖已发送记录。"""
    if not task_ids:
        return {}
    ranked = (
        select(
            notifications.c.task_id,
            notifications.c.sent_at,
            notifications.c.sender_name,
            func.row_number()
            .over(
                partition_by=notifications.c.task_id,
                order_by=(notifications.c.sent_at.desc(), notifications.c.id.desc()),
            )
            .label("rank"),
        )
        .where(
            notifications.c.task_id.in_(task_ids),
            notifications.c.status == "sent",
            notifications.c.sent_at.is_not(None),
        )
        .subquery()
    )
    rows = connection.execute(select(ranked).where(ranked.c.rank == 1)).mappings()
    return {row["task_id"]: dict(row) for row in rows}


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
