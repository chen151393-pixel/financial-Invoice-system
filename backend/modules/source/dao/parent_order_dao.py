"""母采购单头：按 NS 身份新增或更新单号、币种、汇率。"""

from sqlalchemy import insert, select, update

from ..entity import parent_orders

RECORD_TYPE = "purchaseOrder"


def upsert(connection, account, ns_internal_id, values, now):
    """values：order_no、currency、exchange_rate；返回本地 ID。"""
    row = (
        connection.execute(
            select(parent_orders.c.id)
            .where(parent_orders.c.ns_account == account, parent_orders.c.ns_internal_id == ns_internal_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if row is None:
        return connection.execute(
            insert(parent_orders).values(
                ns_account=account,
                ns_internal_id=ns_internal_id,
                ns_record_type=RECORD_TYPE,
                synced_at=now,
                is_active=True,
                created_at=now,
                updated_at=now,
                **values,
            )
        ).inserted_primary_key[0]
    connection.execute(
        update(parent_orders)
        .where(parent_orders.c.id == row["id"])
        .values(synced_at=now, is_active=True, updated_at=now, **values)
    )
    return row["id"]
