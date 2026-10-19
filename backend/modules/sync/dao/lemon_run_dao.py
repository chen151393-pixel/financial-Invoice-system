"""手动拉票记录 DAO，不决定业务状态。"""

from datetime import datetime, timezone

from sqlalchemy import insert, select, update

from ..entity.lemon_run import lemon_runs as table


def get(connection, scope, request_id):
    row = (
        connection.execute(select(table).where(table.c.scope_key == scope, table.c.request_id == request_id))
        .mappings()
        .first()
    )
    return dict(row) if row else None


def latest(connection, scope):
    row = (
        connection.execute(
            select(table).where(table.c.scope_key == scope).order_by(table.c.id.desc()).limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def running(connection, scope, *, asid=None, manual_only=False):
    conditions = [table.c.scope_key == scope, table.c.status == "running"]
    if asid is not None:
        conditions.append(table.c.asid == asid)
    if manual_only:
        conditions.append(table.c.background.is_(False))
    return connection.scalar(select(table.c.id).where(*conditions).limit(1))


def create(connection, values):
    connection.execute(insert(table).values(**values))


def finish(connection, scope, request_id, status, *, result=None, error=None):
    values = {"status": status, "error": error, "updated_at": datetime.now(timezone.utc)}
    if result is not None:
        values["result"] = result
    return connection.execute(
        update(table)
        .where(table.c.scope_key == scope, table.c.request_id == request_id, table.c.status == "running")
        .values(**values)
    ).rowcount
