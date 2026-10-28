from sqlalchemy import select

from ..entity import audit


def add(connection, task_id, action, actor, detail, stamp):
    connection.execute(
        audit.insert().values(
            task_id=task_id, action=action, actor=actor, detail=detail, created_at=stamp, updated_at=stamp
        )
    )


def recent(connection, task_id):
    return [
        dict(row)
        for row in connection.execute(
            select(audit).where(audit.c.task_id == task_id).order_by(audit.c.id.desc()).limit(100)
        ).mappings()
    ]
