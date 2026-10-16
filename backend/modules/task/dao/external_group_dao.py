"""外部群目录查询与版本保存，仅访问 task 表。"""

from sqlalchemy import exists, func, insert, or_, select, update

from ..entity.external_group import external_groups as groups
from ..entity.supplier_group import supplier_groups


def by_chat(connection, chat_id, *, lock=False):
    query = select(groups).where(groups.c.chat_id == chat_id)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def page(connection, query):
    linked = exists(select(supplier_groups.c.id).where(supplier_groups.c.chat_id == groups.c.chat_id))
    where = []
    if query.keyword:
        where.append(
            or_(
                *(
                    c.contains(query.keyword, autoescape=True)
                    for c in (
                        groups.c.group_name,
                        groups.c.owner_name,
                        groups.c.chat_id,
                        groups.c.owner_userid,
                    )
                )
            )
        )
    if query.status != "all":
        where.append(linked if query.status == "bound" else ~linked)
    total = connection.execute(select(func.count()).select_from(groups).where(*where)).scalar_one()
    rows = connection.execute(
        select(groups)
        .where(*where)
        .order_by(groups.c.id.desc())
        .offset((query.page - 1) * query.pageSize)
        .limit(query.pageSize)
    ).mappings()
    return total, [dict(row) for row in rows]


def put(connection, current, values, now):
    if current is None:
        connection.execute(insert(groups).values(**values, version=1, created_at=now, updated_at=now))
    else:
        connection.execute(
            update(groups)
            .where(groups.c.id == current["id"])
            .values(**values, version=current["version"] + 1, updated_at=now)
        )
