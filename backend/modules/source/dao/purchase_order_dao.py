"""子采购单与子采购行。"""

from sqlalchemy import select, update

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


def numbers(connection, ids):
    """子采购单号，按 ID 返回（含已停用，供历史任务展示）。"""
    if not ids:
        return {}
    query = select(purchase_orders.c.id, purchase_orders.c.order_no).where(purchase_orders.c.id.in_(ids))
    return {row.id: row.order_no for row in connection.execute(query)}


def ids_like(connection, keyword, limit):
    """单号包含关键字的子采购单 ID（任务搜索用）。"""
    query = select(purchase_orders.c.id).where(purchase_orders.c.order_no.like(f"%{keyword}%")).limit(limit)
    return list(connection.execute(query).scalars())


def line_names(connection, line_ids):
    """子采购行的品名与规格，按 ID 返回（含已停用）。"""
    if not line_ids:
        return {}
    query = select(
        purchase_order_lines.c.id,
        purchase_order_lines.c.item_name,
        purchase_order_lines.c.declaration_name,
        purchase_order_lines.c.specification,
    ).where(purchase_order_lines.c.id.in_(line_ids))
    return {row.id: dict(row._mapping) for row in connection.execute(query)}


def line_context(connection, line_ids, *, lock=False):
    """子采购行及所属子采购单、供应商、采购公司（发票比对用；含已停用记录，以便判断来源变化）。"""
    if not line_ids:
        return []
    query = (
        select(
            purchase_order_lines,
            purchase_orders.c.ns_account,
            purchase_orders.c.supplier_id,
            purchase_orders.c.company_id,
            purchase_orders.c.parent_order_id,
            purchase_orders.c.parent_relation_status,
            purchase_orders.c.raw_record_id,
            purchase_orders.c.currency_raw_record_id,
            purchase_orders.c.order_no,
            purchase_orders.c.parent_order_no,
            purchase_orders.c.currency,
            purchase_orders.c.currency_source,
            purchase_orders.c.currency_issue,
            purchase_orders.c.is_active.label("order_active"),
            suppliers.c.name.label("supplier_name"),
            suppliers.c.name_normalized.label("supplier_name_normalized"),
            companies.c.name.label("company_name"),
            companies.c.name_normalized.label("company_name_normalized"),
        )
        .select_from(
            purchase_order_lines.join(
                purchase_orders, purchase_orders.c.id == purchase_order_lines.c.purchase_order_id
            )
            .outerjoin(suppliers, suppliers.c.id == purchase_orders.c.supplier_id)
            .outerjoin(companies, companies.c.id == purchase_orders.c.company_id)
        )
        .where(purchase_order_lines.c.id.in_(line_ids))
    )
    if lock:
        query = query.order_by(purchase_order_lines.c.id).with_for_update()
    return [dict(row) for row in connection.execute(query).mappings()]


def inherited_orders(connection, parent_id, values, now):
    ids = list(
        connection.execute(
            select(purchase_orders.c.id)
            .where(purchase_orders.c.parent_order_id == parent_id)
            .order_by(purchase_orders.c.id)
        ).scalars()
    )
    if ids:
        connection.execute(
            update(purchase_orders).where(purchase_orders.c.id.in_(ids)).values(**values, updated_at=now)
        )
    return ids


def all_line_ids(connection, order_ids):
    return (
        list(
            connection.execute(
                select(purchase_order_lines.c.id)
                .where(purchase_order_lines.c.purchase_order_id.in_(order_ids))
                .order_by(purchase_order_lines.c.id)
            ).scalars()
        )
        if order_ids
        else []
    )
