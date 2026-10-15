"""发票行：新增与按发票 / 按行读取。"""

from sqlalchemy import insert, select

from ..entity import items


def insert_items(connection, invoice_id, rows, now):
    if rows:
        connection.execute(
            insert(items),
            [{**row, "invoice_id": invoice_id, "created_at": now, "updated_at": now} for row in rows],
        )


def by_invoices(connection, invoice_ids):
    if not invoice_ids:
        return []
    query = select(items).where(items.c.invoice_id.in_(invoice_ids)).order_by(items.c.invoice_id, items.c.id)
    return [dict(row) for row in connection.execute(query).mappings()]


def by_ids(connection, item_ids):
    if not item_ids:
        return []
    query = select(items).where(items.c.id.in_(item_ids)).order_by(items.c.id)
    return [dict(row) for row in connection.execute(query).mappings()]
