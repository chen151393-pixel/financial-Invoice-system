"""单表人员分工历史；最新记录 ID 兼作并发版本，不保存重复版本字段。"""

from sqlalchemy import func, insert, select

from ..entity import supplier_owners


def associations(connection):
    query = select(
        supplier_owners.c.supplier_id,
        supplier_owners.c.company_id,
        func.max(supplier_owners.c.id).label("revision"),
    )
    return [
        dict(row)
        for row in connection.execute(
            query.group_by(supplier_owners.c.supplier_id, supplier_owners.c.company_id)
        ).mappings()
    ]


def records(connection, supplier_id=None, company_id=None):
    query = select(supplier_owners)
    if supplier_id is not None:
        query = query.where(
            supplier_owners.c.supplier_id == supplier_id, supplier_owners.c.company_id == company_id
        )
    return [
        dict(row)
        for row in connection.execute(
            query.order_by(supplier_owners.c.effective_date, supplier_owners.c.id)
        ).mappings()
    ]


def pair(connection, supplier_id, company_id):
    record_id = connection.execute(
        select(func.max(supplier_owners.c.id)).where(
            supplier_owners.c.supplier_id == supplier_id, supplier_owners.c.company_id == company_id
        )
    ).scalar()
    return {"revision": record_id} if record_id is not None else None


def append(connection, supplier_id, company_id, values, now):
    return connection.execute(
        insert(supplier_owners).values(
            supplier_id=supplier_id, company_id=company_id, created_at=now, **values
        )
    ).inserted_primary_key[0]


def effective(connection, supplier_id, company_id, day):
    query = (
        select(supplier_owners)
        .where(
            supplier_owners.c.supplier_id == supplier_id,
            supplier_owners.c.company_id == company_id,
            supplier_owners.c.effective_date <= day,
        )
        .order_by(supplier_owners.c.effective_date.desc(), supplier_owners.c.id.desc())
        .limit(1)
    )
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None
