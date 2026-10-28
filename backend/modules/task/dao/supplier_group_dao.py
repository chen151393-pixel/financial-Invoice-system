"""供应商默认企微群：按供应商查询、分页与带版本保存。"""

from sqlalchemy import func, insert, or_, select, update

from ..entity import supplier_groups


def by_supplier(connection, supplier_id, *, lock=False):
    query = select(supplier_groups).where(supplier_groups.c.supplier_id == supplier_id)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def by_suppliers(connection, supplier_ids):
    query = select(supplier_groups).where(supplier_groups.c.supplier_id.in_(supplier_ids))
    return {row["supplier_id"]: dict(row) for row in connection.execute(query).mappings()}


def page(connection, *, status, keyword, supplier_ids, offset, limit):
    """status：all / enabled / disabled；关键字匹配群名或供应商（调用方先按名称查出供应商 ID）。"""
    where = []
    if status != "all":
        where.append(supplier_groups.c.enabled.is_(status == "enabled"))
    if keyword:
        matches = [
            column.contains(keyword, autoescape=True)
            for column in (
                supplier_groups.c.group_name,
                supplier_groups.c.chat_id,
                supplier_groups.c.owner_name,
                supplier_groups.c.owner_userid,
            )
        ]
        if supplier_ids:
            matches.append(supplier_groups.c.supplier_id.in_(supplier_ids))
        where.append(or_(*matches))
    total = connection.execute(select(func.count()).select_from(supplier_groups).where(*where)).scalar()
    query = (
        select(supplier_groups)
        .where(*where)
        .order_by(supplier_groups.c.updated_at.desc(), supplier_groups.c.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return total, [dict(row) for row in connection.execute(query).mappings()]


def supplier_ids(connection, *, enabled=None, keyword="", group_names=(), owners=()):
    query = select(supplier_groups.c.supplier_id)
    if enabled is not None:
        query = query.where(supplier_groups.c.enabled.is_(enabled))
    if group_names:
        query = query.where(
            or_(*(supplier_groups.c.group_name.contains(term, autoescape=True) for term in group_names))
        )
    if owners:
        query = query.where(
            or_(
                *(
                    column.contains(term, autoescape=True)
                    for term in owners
                    for column in (supplier_groups.c.owner_name, supplier_groups.c.owner_userid)
                )
            )
        )
    if keyword:
        query = query.where(
            or_(
                *(
                    column.contains(keyword, autoescape=True)
                    for column in (
                        supplier_groups.c.group_name,
                        supplier_groups.c.chat_id,
                        supplier_groups.c.owner_name,
                        supplier_groups.c.owner_userid,
                    )
                )
            )
        )
    return list(connection.execute(query).scalars())


def insert_group(connection, values, now):
    connection.execute(insert(supplier_groups).values(version=1, created_at=now, updated_at=now, **values))


def update_group(connection, group_id, version, values, now):
    """版本一致才更新；返回是否更新成功。"""
    result = connection.execute(
        update(supplier_groups)
        .where(supplier_groups.c.id == group_id, supplier_groups.c.version == version)
        .values(version=version + 1, updated_at=now, **values)
    )
    return result.rowcount == 1


def by_chats(connection, chat_ids):
    query = select(supplier_groups).where(supplier_groups.c.chat_id.in_(chat_ids))
    return [dict(row) for row in connection.execute(query).mappings()]
