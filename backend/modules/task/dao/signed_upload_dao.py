"""回签上传队列存取；状态决策由 Service 管理。"""

from sqlalchemy import func, insert, select, update

from ..entity import signed_upload_jobs as jobs


def create(connection, rows):
    connection.execute(insert(jobs), rows)


def batch(connection, actor, batch_id):
    return [
        dict(r)
        for r in connection.execute(
            select(jobs).where(jobs.c.actor == actor, jobs.c.batch_id == batch_id).order_by(jobs.c.position)
        ).mappings()
    ]


def get(connection, actor, batch_id, file_id):
    row = (
        connection.execute(
            select(jobs).where(jobs.c.id == file_id, jobs.c.actor == actor, jobs.c.batch_id == batch_id)
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def change(connection, file_id, **values):
    connection.execute(update(jobs).where(jobs.c.id == file_id).values(**values))


def pending(connection):
    return [
        dict(r)
        for r in connection.execute(
            select(jobs)
            .where(jobs.c.status.in_(["queued", "running"]))
            .order_by(jobs.c.created_at, jobs.c.position)
            .limit(20)
        ).mappings()
    ]


def recent_batches(connection, actor):
    return list(
        connection.execute(
            select(jobs.c.batch_id)
            .where(jobs.c.actor == actor)
            .group_by(jobs.c.batch_id)
            .order_by(func.max(jobs.c.created_at).desc())
            .limit(20)
        ).scalars()
    )
