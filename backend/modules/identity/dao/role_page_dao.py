"""只读写角色页面配置；事务与版本校验归服务。"""

from sqlalchemy import insert, select, update

from ..entity.role_page import role_pages


def configurations(connection):
    return {row["role"]: dict(row) for row in connection.execute(select(role_pages)).mappings()}


def save(connection, role, pages, revision, actor, now):
    values = {"pages": pages, "revision": revision + 1, "updated_by": actor, "updated_at": now}
    if revision == 0:
        connection.execute(insert(role_pages).values(role=role, created_at=now, **values))
    else:
        connection.execute(update(role_pages).where(role_pages.c.role == role).values(**values))
