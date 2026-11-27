"""销售合同记录读写；不提交事务。"""

from sqlalchemy import delete, insert, select

from ..entity.contract import settlement_contracts as contracts
from .document_scope import belongs, condition, conditions
from .document_scope import values as scope_values


def of_batch(connection, batch_id):
    query = select(contracts).where(condition(contracts, batch_id)).order_by(contracts.c.contract_no)
    return [dict(row) for row in connection.execute(query).mappings()]


def by_scopes(connection, references):
    result = {reference: [] for reference in references}
    if references:
        query = select(contracts).where(conditions(contracts, references)).order_by(contracts.c.contract_no)
        rows = [dict(row) for row in connection.execute(query).mappings()]
        for reference in references:
            result[reference] = [row for row in rows if belongs(row, reference)]
    return result


def direct_owners(connection, numbers):
    """已生成合同的直接收汇报关单号集合。"""
    if not numbers:
        return set()
    query = select(contracts.c.direct_declaration_no).where(contracts.c.direct_declaration_no.in_(numbers))
    return {row[0] for row in connection.execute(query)}


def get(connection, batch_id, contract_id):
    query = select(contracts).where(contracts.c.id == contract_id, condition(contracts, batch_id))
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def replace(connection, batch_id, rows, now):
    """重新生成：整批替换该批次的合同记录。"""
    connection.execute(delete(contracts).where(condition(contracts, batch_id)))
    if rows:
        connection.execute(
            insert(contracts),
            [{**row, **scope_values(batch_id), "created_at": now, "updated_at": now} for row in rows],
        )


def by_groups(connection, group_ids):
    result = {group_id: [] for group_id in group_ids}
    if group_ids:
        query = (
            select(contracts)
            .where(contracts.c.document_group_id.in_(group_ids))
            .order_by(contracts.c.contract_no)
        )
        for row in connection.execute(query).mappings():
            result[row["document_group_id"]].append(dict(row))
    return result
