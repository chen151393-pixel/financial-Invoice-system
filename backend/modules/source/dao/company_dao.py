"""采购公司主数据：按 NS 身份新增或更新名称。"""

from sqlalchemy import insert, select, update

from ..entity import companies
from ..policy.names import normalize_name


def upsert(connection, account, party, now):
    row = (
        connection.execute(
            select(companies.c.id, companies.c.name)
            .where(companies.c.ns_account == account, companies.c.ns_internal_id == party["ns_internal_id"])
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
            insert(companies).values(
                ns_account=account,
                ns_internal_id=party["ns_internal_id"],
                created_at=now,
                updated_at=now,
                **values,
            )
        ).inserted_primary_key[0]
    if row["name"] != party["name"]:
        connection.execute(
            update(companies).where(companies.c.id == row["id"]).values(updated_at=now, **values)
        )
    return row["id"]


def names(connection, ids):
    """采购公司名称，按 ID 返回（含已停用，供历史任务展示）。"""
    if not ids:
        return {}
    query = select(companies.c.id, companies.c.name).where(companies.c.id.in_(ids))
    return {row.id: row.name for row in connection.execute(query)}
