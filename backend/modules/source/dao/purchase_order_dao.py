"""子采购单与子采购行。"""

from sqlalchemy import select

from ..entity import companies, purchase_order_lines, purchase_orders, raw_records, suppliers
from . import document_dao


def save(connection, account, document, now):
    return document_dao.save(
        connection,
        purchase_orders,
        purchase_order_lines,
        "purchase_order_id",
        account,
        document["ns_internal_id"],
        document["head"],
        document["lines"],
        now,
    )


def find_ids(connection, account, ns_ids):
    if not ns_ids:
        return {}
    rows = connection.execute(
        select(purchase_orders.c.ns_internal_id, purchase_orders.c.id).where(
            purchase_orders.c.ns_account == account, purchase_orders.c.ns_internal_id.in_(ns_ids)
        )
    )
    return {row.ns_internal_id: row.id for row in rows}


def orders(connection, ids):
    """有效子采购单及供应商、公司名称和原始数据。"""
    if not ids:
        return []
    query = (
        select(
            purchase_orders,
            suppliers.c.name.label("supplier_name"),
            suppliers.c.ns_internal_id.label("supplier_ns_id"),
            companies.c.name.label("company_name"),
            companies.c.ns_internal_id.label("company_ns_id"),
            raw_records.c.payload.label("raw_payload"),
        )
        .select_from(
            purchase_orders.outerjoin(suppliers, suppliers.c.id == purchase_orders.c.supplier_id)
            .outerjoin(companies, companies.c.id == purchase_orders.c.company_id)
            .outerjoin(raw_records, raw_records.c.id == purchase_orders.c.raw_record_id)
        )
        .where(purchase_orders.c.id.in_(ids), purchase_orders.c.is_active.is_(True))
        .order_by(purchase_orders.c.order_no, purchase_orders.c.id)
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def lines(connection, order_ids):
    if not order_ids:
        return []
    query = (
        select(purchase_order_lines)
        .where(
            purchase_order_lines.c.purchase_order_id.in_(order_ids),
            purchase_order_lines.c.is_active.is_(True),
        )
        .order_by(purchase_order_lines.c.purchase_order_id, purchase_order_lines.c.id)
    )
    return [dict(row) for row in connection.execute(query).mappings()]
