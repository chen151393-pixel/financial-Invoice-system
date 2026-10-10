"""报关单与报关明细。"""

from sqlalchemy import func, or_, select, update

from ..entity import companies, customs_declarations, customs_lines, raw_records
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


def page(connection, account, keyword, offset, limit):
    """有效报关单分页；关键字匹配 CD 编号、真实报关单号或明细 PL。"""
    conditions = [customs_declarations.c.is_active.is_(True)]
    if account:
        conditions.append(customs_declarations.c.ns_account == account)
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
