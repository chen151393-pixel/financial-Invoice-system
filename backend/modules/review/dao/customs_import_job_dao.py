"""导入作业持久状态；事务由 Service 管理。"""

from sqlalchemy import insert, select, update

from ..entity.customs_import_job import customs_import_jobs as jobs


def enqueue(connection, filename, upload_key, actor, now):
    result = connection.execute(
        insert(jobs).values(
            file_name=filename,
            upload_key=upload_key,
            actor=actor,
            status="pending",
            created_at=now,
            updated_at=now,
        )
    )
    return result.inserted_primary_key[0]


def get(connection, job_id):
    row = connection.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
    return dict(row) if row else None


def recent(connection, actor):
    # 未完成作业不因后续上传被挤出最近记录，便于关闭弹窗/刷新页面后继续跟踪。
    active = jobs.c.status.in_(("pending", "running"))
    query = select(jobs).where(jobs.c.actor == actor)
    pending = connection.execute(query.where(active).order_by(jobs.c.id)).mappings()
    rows = [dict(row) for row in pending]
    history = connection.execute(query.where(~active).order_by(jobs.c.id.desc()).limit(10)).mappings()
    return rows + [dict(row) for row in history]


def next_pending(connection):
    query = select(jobs).where(jobs.c.status.in_(("pending", "running"))).order_by(jobs.c.id).limit(1)
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def running(connection, job_id, now):
    connection.execute(update(jobs).where(jobs.c.id == job_id).values(status="running", updated_at=now))


def finish(connection, job_id, now, *, result=None, error=None):
    connection.execute(
        update(jobs)
        .where(
            jobs.c.id == job_id,
            jobs.c.status.in_(("pending", "running")),
        )
        .values(
            status="failed" if error else "completed",
            result=result,
            error_message=error[:1000] if error else None,
            updated_at=now,
        )
    )
