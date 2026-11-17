"""结汇批次明细读写；不提交事务。"""

from sqlalchemy import insert, select, update

from ..entity.batch_item import settlement_batch_items as items

ITEM_FIELDS = (
    "declaration_no",
    "record_no",
    "receipt_id",
    "receipt_revision",
    "sales_orders",
    "consignee",
    "export_date",
    "currency",
    "declared_amount",
)


def insert_items(connection, batch_id, rows, now):
    connection.execute(
        insert(items),
        [
            {
                **{field: row.get(field) for field in ITEM_FIELDS},
                "batch_id": batch_id,
                "active_declaration_no": row["declaration_no"],
                "created_at": now,
                "updated_at": now,
            }
            for row in rows
        ],
    )


def of_batches(connection, batch_ids):
    """{批次 ID: [明细, ...]}，按报关单号排序。"""
    if not batch_ids:
        return {}
    query = (
        select(items)
        .where(items.c.batch_id.in_(batch_ids))
        .order_by(items.c.batch_id, items.c.declaration_no)
    )
    result = {batch_id: [] for batch_id in batch_ids}
    for row in connection.execute(query).mappings():
        result[row["batch_id"]].append(dict(row))
    return result


def active_by_numbers(connection, numbers, *, lock=False):
    """已被有效批次占用的报关单：{报关单号: 批次 ID}。"""
    if not numbers:
        return {}
    query = select(items.c.active_declaration_no, items.c.batch_id).where(
        items.c.active_declaration_no.in_(numbers)
    )
    if lock:
        query = query.with_for_update()
    return {number: batch_id for number, batch_id in connection.execute(query)}


def active_numbers(connection):
    """全部被有效批次占用的报关单号与所属批次。"""
    query = select(items.c.active_declaration_no, items.c.batch_id).where(
        items.c.active_declaration_no.is_not(None)
    )
    return {number: batch_id for number, batch_id in connection.execute(query)}


def release(connection, batch_id, now):
    """批次作废后释放报关单，允许重新建批次。"""
    connection.execute(
        update(items).where(items.c.batch_id == batch_id).values(active_declaration_no=None, updated_at=now)
    )


def batch_ids_by_declaration(connection, number):
    query = select(items.c.batch_id).where(items.c.declaration_no.contains(number, autoescape=True))
    return [row[0] for row in connection.execute(query)]
