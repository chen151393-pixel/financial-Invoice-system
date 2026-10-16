"""发票行：新增与按发票 / 按行读取。"""

from sqlalchemy import insert, select, update

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


def replace_projection(connection, invoice_id, rows, identity, now):
    previous = by_invoices(connection, [invoice_id])
    existing = {identity(r): r for r in previous if r["is_active"]}
    connection.execute(
        update(items).where(items.c.invoice_id == invoice_id).values(is_active=False, updated_at=now)
    )
    for index, row in enumerate(rows):
        old = existing.get(identity(row))
        if old:
            values = {k: v for k, v in row.items() if k != "source_line_key"}
            connection.execute(
                update(items).where(items.c.id == old["id"]).values(**values, is_active=True, updated_at=now)
            )
        else:
            # 来源键是导入散列，不能复用被停用的历史逻辑行；新键带稳定序号隔离。
            insert_items(
                connection,
                invoice_id,
                [{**row, "source_line_key": f"version:{len(previous)}:{index}:{now.isoformat()}"}],
                now,
            )
