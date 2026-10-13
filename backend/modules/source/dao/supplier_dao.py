"""供应商主数据：按 NS 身份新增或更新名称。"""

from sqlalchemy import func, insert, select, update

from ..entity import suppliers
from ..policy.names import normalize_name


def upsert(connection, account, party, now):
    row = (
        connection.execute(
            select(suppliers.c.id, suppliers.c.name)
            .where(suppliers.c.ns_account == account, suppliers.c.ns_internal_id == party["ns_internal_id"])
            .with_for_update()
        )
        .mappings()
        .first()
    )
    values = {
        "name": party["name"],
        "name_normalized": normalize_name(party["name"])[:255],
        "is_active": True,
    }
    if row is None:
        return connection.execute(
            insert(suppliers).values(
                ns_account=account,
                ns_internal_id=party["ns_internal_id"],
                created_at=now,
                updated_at=now,
                **values,
            )
        ).inserted_primary_key[0]
    if row["name"] != party["name"]:
        connection.execute(
            update(suppliers).where(suppliers.c.id == row["id"]).values(updated_at=now, **values)
        )
    return row["id"]


def names(connection, ids):
    """供应商名称与账套，按 ID 返回（含已停用，供历史任务展示）。"""
    if not ids:
        return {}
    query = select(suppliers.c.id, suppliers.c.name, suppliers.c.ns_account, suppliers.c.is_active).where(
        suppliers.c.id.in_(ids)
    )
    return {
        row.id: {"name": row.name, "ns_account": row.ns_account, "active": bool(row.is_active)}
        for row in connection.execute(query)
    }


def ids_like(connection, keyword, limit):
    """名称包含关键字的供应商 ID（任务搜索用）。"""
    query = select(suppliers.c.id).where(suppliers.c.name.like(f"%{keyword}%")).limit(limit)
    return list(connection.execute(query).scalars())


def page(connection, account, keyword, offset, limit):
    """有效供应商分页（供应商群配置选择用）。"""
    conditions = [suppliers.c.is_active.is_(True)]
    if account:
        conditions.append(suppliers.c.ns_account == account)
    if keyword:
        conditions.append(suppliers.c.name.like(f"%{keyword}%"))
    total = connection.execute(select(func.count()).select_from(suppliers).where(*conditions)).scalar()
    query = (
        select(suppliers.c.id, suppliers.c.ns_account, suppliers.c.name)
        .where(*conditions)
        .order_by(suppliers.c.name, suppliers.c.id)
        .offset(offset)
        .limit(limit)
    )
    return total, [dict(row) for row in connection.execute(query).mappings()]
