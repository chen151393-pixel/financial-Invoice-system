"""同步计划持久化；调用方持有绑定行锁后修改。"""

from sqlalchemy import insert, select, update

from ..entity.lemon_plan import lemon_plans as table


def get(connection, scope):
    row = connection.execute(select(table).where(table.c.scope_key == scope)).mappings().first()
    return dict(row) if row else None


def save(connection, scope, values):
    if get(connection, scope):
        connection.execute(update(table).where(table.c.scope_key == scope).values(**values))
    else:
        connection.execute(insert(table).values(scope_key=scope, **values))


def due(connection, scope, now, *, lock=False):
    query = select(table).where(
        table.c.scope_key == scope, table.c.enabled.is_(True), table.c.next_run_at <= now
    )
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None
