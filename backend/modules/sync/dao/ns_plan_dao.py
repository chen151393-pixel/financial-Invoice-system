"""NS 定时计划持久化；不决定业务状态、不自行提交。"""

from sqlalchemy import insert, select, update

from ..entity.ns_plan import ns_plans as table


def get(connection, scope, *, lock=False):
    query = select(table).where(table.c.scope_key == scope)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def create(connection, scope, values):
    connection.execute(insert(table).values(scope_key=scope, **values))


def change(connection, scope, values):
    connection.execute(update(table).where(table.c.scope_key == scope).values(**values))


def due(connection, scope, now, *, lock=False):
    query = select(table).where(
        table.c.scope_key == scope, table.c.enabled.is_(True), table.c.next_run_at <= now
    )
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None
