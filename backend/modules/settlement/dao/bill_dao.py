"""提单读写；不提交事务。"""

from sqlalchemy import insert, select, update

from ..entity.bill import settlement_bills as bills
from .document_scope import belongs, condition, conditions


def active(connection, batch_id):
    """批次未移除的提单，按上传顺序。"""
    query = select(bills).where(condition(bills, batch_id), bills.c.removed_at.is_(None)).order_by(bills.c.id)
    return [dict(row) for row in connection.execute(query).mappings()]


def by_scopes(connection, references):
    result = {reference: [] for reference in references}
    if references:
        query = (
            select(bills)
            .where(conditions(bills, references), bills.c.removed_at.is_(None))
            .order_by(bills.c.id)
        )
        rows = [dict(row) for row in connection.execute(query).mappings()]
        for reference in references:
            result[reference] = [row for row in rows if belongs(row, reference)]
    return result


def direct_owners(connection, numbers):
    """已有未移除提单的直接收汇报关单号集合。"""
    if not numbers:
        return set()
    query = select(bills.c.direct_declaration_no).where(
        bills.c.direct_declaration_no.in_(numbers), bills.c.removed_at.is_(None)
    )
    return {row[0] for row in connection.execute(query)}


def get(connection, batch_id, bill_id):
    query = select(bills).where(bills.c.id == bill_id, condition(bills, batch_id))
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def insert_bill(connection, values, now):
    result = connection.execute(insert(bills).values(**values, created_at=now, updated_at=now))
    return result.inserted_primary_key[0]


def update_bill(connection, bill_id, values, now):
    connection.execute(update(bills).where(bills.c.id == bill_id).values(**values, updated_at=now))


def by_groups(connection, group_ids):
    result = {group_id: [] for group_id in group_ids}
    if group_ids:
        query = (
            select(bills)
            .where(bills.c.document_group_id.in_(group_ids), bills.c.removed_at.is_(None))
            .order_by(bills.c.id)
        )
        for row in connection.execute(query).mappings():
            result[row["document_group_id"]].append(dict(row))
    return result
