"""报关单与子采购单的关联（单头级、行级）。失效关联置为 stale，不删除。"""

from sqlalchemy import func, insert, select, update

from ..entity import customs_lines
from ..entity import customs_purchase_links as links


def active(connection, declaration_id):
    query = (
        select(links)
        .where(links.c.customs_declaration_id == declaration_id, links.c.status == "active")
        .order_by(links.c.id)
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def declared_lines(connection, purchase_line_ids):
    """子采购行的有效行级报关关联及报关行申报信息（报关单位、报关数量、申报单价、金额、币种、销售订单号）。"""
    if not purchase_line_ids:
        return []
    query = (
        select(
            links.c.purchase_line_id,
            links.c.purchase_order_id,
            links.c.customs_line_id,
            customs_lines.c.sales_order_no,
            customs_lines.c.declared_unit,
            customs_lines.c.declared_quantity,
            customs_lines.c.declared_unit_price,
            customs_lines.c.amount,
            customs_lines.c.currency,
        )
        .join(customs_lines, customs_lines.c.id == links.c.customs_line_id)
        .where(
            links.c.purchase_line_id.in_(purchase_line_ids),
            links.c.status == "active",
            customs_lines.c.is_active.is_(True),
        )
        .order_by(links.c.purchase_line_id)
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def upsert_active(connection, declaration_id, order_id, customs_line_id, purchase_line_id, evidence, now):
    existing = connection.execute(
        select(links.c.id).where(
            links.c.customs_declaration_id == declaration_id,
            links.c.purchase_order_id == order_id,
            links.c.customs_line_key == (customs_line_id or 0),
            links.c.purchase_line_key == (purchase_line_id or 0),
        )
    ).scalar()
    values = {"evidence": evidence, "status": "active", "synced_at": now, "updated_at": now}
    if existing is None:
        connection.execute(
            insert(links).values(
                customs_declaration_id=declaration_id,
                purchase_order_id=order_id,
                customs_line_id=customs_line_id,
                purchase_line_id=purchase_line_id,
                created_at=now,
                **values,
            )
        )
    else:
        connection.execute(update(links).where(links.c.id == existing).values(**values))


def mark_stale(connection, ids, now):
    if ids:
        connection.execute(update(links).where(links.c.id.in_(ids)).values(status="stale", updated_at=now))


def active_of_orders(connection, order_ids):
    """这些子采购单当前全部有效关联。"""
    if not order_ids:
        return []
    query = select(links).where(links.c.purchase_order_id.in_(order_ids), links.c.status == "active")
    return [dict(row) for row in connection.execute(query).mappings()]


def declarations_of_orders(connection, order_ids):
    if not order_ids:
        return set()
    query = select(func.distinct(links.c.customs_declaration_id)).where(
        links.c.purchase_order_id.in_(order_ids), links.c.status == "active"
    )
    return set(connection.execute(query).scalars())
