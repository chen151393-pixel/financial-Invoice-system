"""批次记录及分页查询，仅访问 sync 表。"""

from sqlalchemy import func, insert, select, update

from ..entity.sync_run import sync_runs as table


def get(connection, scope, request_id, *, lock=False):
    query = select(table).where(table.c.scope_key == scope, table.c.request_id == request_id)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def create(connection, values):
    return connection.execute(insert(table).values(**values)).inserted_primary_key[0]


def change(connection, run_id, **values):
    connection.execute(update(table).where(table.c.id == run_id).values(**values))


def list_page(connection, scope, page, size, phase=None):
    conditions = [table.c.scope_key == scope]
    if phase:
        conditions.append(table.c.phase == phase)
    total = connection.scalar(select(func.count()).select_from(table).where(*conditions))
    rows = connection.execute(
        select(table).where(*conditions).order_by(table.c.id.desc()).offset((page - 1) * size).limit(size)
    ).mappings()
    return [dict(row) for row in rows], total


def active(connection, scope, phases):
    return [
        dict(row)
        for row in connection.execute(
            select(table).where(table.c.scope_key == scope, table.c.phase.in_(phases)).order_by(table.c.id)
        ).mappings()
    ]


def counts(connection, scope):
    rows = connection.execute(
        select(table.c.phase, func.count()).where(table.c.scope_key == scope).group_by(table.c.phase)
    )
    return {phase: count for phase, count in rows}


def since(connection, start):
    """start（UTC）之后开始的同步批次：时间、来源与批次状态，供同步情况统计。"""
    query = select(table.c.started_at, table.c.source, table.c.phase).where(table.c.started_at >= start)
    return [dict(row) for row in connection.execute(query).mappings()]
