"""飞书部门与成员同步记录。"""

from sqlalchemy import insert, select, update

from ..entity import sync_runs


def start(connection, trigger, actor, now):
    result = connection.execute(
        insert(sync_runs).values(
            trigger=trigger,
            started_by=actor,
            status="running",
            started_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    return result.inserted_primary_key[0]


def finish(connection, run_id, values, now):
    connection.execute(
        update(sync_runs).where(sync_runs.c.id == run_id).values(finished_at=now, updated_at=now, **values)
    )


def latest(connection, *, status=None):
    query = select(sync_runs).order_by(sync_runs.c.id.desc()).limit(1)
    if status:
        query = query.where(sync_runs.c.status == status)
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None
