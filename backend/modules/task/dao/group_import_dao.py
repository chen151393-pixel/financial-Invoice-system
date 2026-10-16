"""导入快照、确认留痕；事务由服务层管理。"""

from sqlalchemy import insert, select, update

from ..entity.group_import import group_imports


def create(connection, values):
    connection.execute(insert(group_imports).values(**values))


def get(connection, import_id, *, lock=False):
    query = select(group_imports).where(group_imports.c.id == import_id)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def confirm(connection, import_id, confirmation, now):
    connection.execute(
        update(group_imports)
        .where(group_imports.c.id == import_id)
        .values(status="confirmed", confirmation=confirmation, updated_at=now)
    )
