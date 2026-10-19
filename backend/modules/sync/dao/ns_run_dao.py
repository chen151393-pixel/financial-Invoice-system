"""NS 按批后台保存记录 DAO，不决定业务状态、不自行提交。"""

from datetime import datetime, timezone

from sqlalchemy import insert, select, update

from ..entity.ns_run import ns_runs as table


def get(connection, scope, request_id):
    row = (
        connection.execute(select(table).where(table.c.scope_key == scope, table.c.request_id == request_id))
        .mappings()
        .first()
    )
    return dict(row) if row else None


def create(connection, values):
    connection.execute(insert(table).values(**values))


def finish(connection, scope, request_id, status, *, result=None, error=None):
    """只从 running 结束；已结束的记录不被覆盖，返回受影响行数供调用方核对。"""
    return connection.execute(
        update(table)
        .where(table.c.scope_key == scope, table.c.request_id == request_id, table.c.status == "running")
        .values(status=status, result=result, error=error, updated_at=datetime.now(timezone.utc))
    ).rowcount
