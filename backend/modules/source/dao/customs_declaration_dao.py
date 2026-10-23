"""报关单与报关明细。"""

from sqlalchemy import func, or_, select, update

from ..entity import (
    companies,
    customs_declarations,
    customs_lines,
    customs_purchase_links,
    purchase_orders,
    raw_records,
    suppliers,
)
from . import document_dao


def save(connection, account, document, now):
    return document_dao.save(
        connection,
        customs_declarations,
        customs_lines,
        "customs_declaration_id",
        account,
        document["ns_internal_id"],
        document["head"],
        [line["row"] for line in document["lines"]],
        now,
    )


def find_ids(connection, account, ns_ids):
    if not ns_ids:
        return {}
    rows = connection.execute(
        select(customs_declarations.c.ns_internal_id, customs_declarations.c.id).where(
            customs_declarations.c.ns_account == account, customs_declarations.c.ns_internal_id.in_(ns_ids)
        )
    )
    return {row.ns_internal_id: row.id for row in rows}


def update_relation(connection, declaration_id, status, issues, now):
    connection.execute(
        update(customs_declarations)
        .where(customs_declarations.c.id == declaration_id)
        .values(relation_status=status, relation_issues=issues, updated_at=now)
    )


def update_digest(connection, declaration_id, digest, now):
    connection.execute(
        update(customs_declarations)
        .where(customs_declarations.c.id == declaration_id)
        .values(content_sha256=digest, updated_at=now)
    )


def _head_query():
    return select(
        customs_declarations,
        companies.c.name.label("declarant_name"),
        raw_records.c.payload.label("raw_payload"),
    ).select_from(
        customs_declarations.outerjoin(
            companies, companies.c.id == customs_declarations.c.declarant_company_id
        ).outerjoin(raw_records, raw_records.c.id == customs_declarations.c.raw_record_id)
    )


def head(connection, declaration_id, *, lock=False):
    query = _head_query().where(customs_declarations.c.id == declaration_id)
    if lock:
        query = query.with_for_update(of=customs_declarations)
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def _supplier_declarations(supplier_id):
    """有效关联中含该供应商子采购单的报关单 ID。"""
    return (
        select(customs_purchase_links.c.customs_declaration_id)
        .join(purchase_orders, purchase_orders.c.id == customs_purchase_links.c.purchase_order_id)
        .where(customs_purchase_links.c.status == "active", purchase_orders.c.supplier_id == supplier_id)
    )


def _conditions(account, keyword, supplier_id=None):
    """有效报关单；关键字匹配 CD 编号、真实报关单号或明细 PL；可按供应商筛选。"""
    conditions = [customs_declarations.c.is_active.is_(True)]
    if account:
        conditions.append(customs_declarations.c.ns_account == account)
    if supplier_id:
        conditions.append(customs_declarations.c.id.in_(_supplier_declarations(supplier_id)))
    if keyword:
        like = f"%{keyword}%"
        pl_match = select(customs_lines.c.customs_declaration_id).where(
            customs_lines.c.pl_no.like(like), customs_lines.c.is_active.is_(True)
        )
        conditions.append(
            or_(
                customs_declarations.c.record_no.like(like),
                customs_declarations.c.declaration_no.like(like),
                customs_declarations.c.id.in_(pl_match),
            )
        )
    return conditions


def index(connection, account, keyword, supplier_id=None):
    """符合条件的全部报关单：ID、真实报关单号、内容摘要、有效关联的子采购单数，按申报日期倒序。"""
    linked = (
        select(func.count(func.distinct(customs_purchase_links.c.purchase_order_id)))
        .where(
            customs_purchase_links.c.customs_declaration_id == customs_declarations.c.id,
            customs_purchase_links.c.status == "active",
        )
        .scalar_subquery()
    )
    query = (
        select(
            customs_declarations.c.id,
            customs_declarations.c.declaration_no,
            customs_declarations.c.content_sha256,
            linked.label("order_count"),
        )
        .where(*_conditions(account, keyword, supplier_id))
        .order_by(customs_declarations.c.declaration_date.desc(), customs_declarations.c.id.desc())
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def accounts(connection):
    query = (
        select(customs_declarations.c.ns_account)
        .where(customs_declarations.c.is_active.is_(True))
        .distinct()
        .order_by(customs_declarations.c.ns_account)
    )
    return list(connection.execute(query).scalars())


def suppliers_of(connection, account):
    """有效报关单关联到的供应商（供筛选下拉使用），按名称排序。"""
    query = (
        select(suppliers.c.id, suppliers.c.name)
        .distinct()
        .select_from(
            customs_purchase_links.join(
                purchase_orders, purchase_orders.c.id == customs_purchase_links.c.purchase_order_id
            )
            .join(suppliers, suppliers.c.id == purchase_orders.c.supplier_id)
            .join(
                customs_declarations,
                customs_declarations.c.id == customs_purchase_links.c.customs_declaration_id,
            )
        )
        .where(*_conditions(account, ""), customs_purchase_links.c.status == "active")
        .order_by(suppliers.c.name, suppliers.c.id)
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def page(connection, account, keyword, offset, limit):
    """有效报关单分页。"""
    conditions = _conditions(account, keyword)
    total = connection.execute(
        select(func.count()).select_from(customs_declarations).where(*conditions)
    ).scalar()
    query = (
        _head_query()
        .where(*conditions)
        .order_by(customs_declarations.c.declaration_date.desc(), customs_declarations.c.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return total, [dict(row) for row in connection.execute(query).mappings()]


def lines(connection, declaration_id):
    query = (
        select(customs_lines, companies.c.name.label("company_name"))
        .select_from(customs_lines.outerjoin(companies, companies.c.id == customs_lines.c.company_id))
        .where(customs_lines.c.customs_declaration_id == declaration_id, customs_lines.c.is_active.is_(True))
        .order_by(customs_lines.c.id)
    )
    return [dict(row) for row in connection.execute(query).mappings()]
