"""销售单头：按 NS 身份新增或更新单号、币种、汇率。"""

from sqlalchemy import insert, select, update

from ..entity import sales_orders


def upsert(connection, account, ns_internal_id, values, now):
    """values：order_no、currency、currency_name、exchange_rate；返回本地 ID。"""
    row = (
        connection.execute(
            select(sales_orders.c.id)
            .where(sales_orders.c.ns_account == account, sales_orders.c.ns_internal_id == ns_internal_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if row is None:
        return connection.execute(
            insert(sales_orders).values(
                ns_account=account,
                ns_internal_id=ns_internal_id,
                synced_at=now,
                created_at=now,
                updated_at=now,
                **values,
            )
        ).inserted_primary_key[0]
    connection.execute(
        update(sales_orders)
        .where(sales_orders.c.id == row["id"])
        .values(synced_at=now, updated_at=now, **values)
    )
    return row["id"]


def by_ids(connection, ids):
    if not ids:
        return {}
    query = select(sales_orders).where(sales_orders.c.id.in_(sorted(set(ids))))
    return {row["id"]: dict(row) for row in connection.execute(query).mappings()}
