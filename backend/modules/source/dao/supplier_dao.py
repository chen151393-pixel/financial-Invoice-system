"""供应商主数据：按 NS 身份新增或更新名称。"""

from sqlalchemy import insert, select, update

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
