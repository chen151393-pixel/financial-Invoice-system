"""资料组及成员读写、单票旧资料归组；事务由 Service 管理。"""

from sqlalchemy import func, insert, select, update

from ..entity.bill import settlement_bills as bills
from ..entity.contract import settlement_contracts as contracts
from ..entity.document_group import settlement_document_group_items as items
from ..entity.document_group import settlement_document_groups as groups


def by_numbers(connection, numbers):
    if not numbers:
        return {}
    query = (
        select(items.c.declaration_no, groups)
        .join(groups, groups.c.id == items.c.group_id)
        .where(items.c.declaration_no.in_(numbers))
    )
    return {r["declaration_no"]: dict(r) for r in connection.execute(query).mappings()}


def get(connection, group_id):
    row = connection.execute(select(groups).where(groups.c.id == group_id)).mappings().first()
    return dict(row) if row else None


def by_request(connection, request_id):
    row = connection.execute(select(groups).where(groups.c.request_id == request_id)).mappings().first()
    return dict(row) if row else None


def all_groups(connection, grouping="all"):
    counts = (
        select(items.c.group_id, func.count().label("member_count")).group_by(items.c.group_id).subquery()
    )
    query = (
        select(groups).join(counts, counts.c.group_id == groups.c.id).where(groups.c.merged_into_id.is_(None))
    )
    if grouping == "single":
        query = query.where(counts.c.member_count == 1)
    elif grouping == "multiple":
        query = query.where(counts.c.member_count > 1)
    return [dict(row) for row in connection.execute(query.order_by(groups.c.id.desc())).mappings()]


def numbers(connection, group_id):
    return list(
        connection.execute(
            select(items.c.declaration_no).where(items.c.group_id == group_id).order_by(items.c.id)
        ).scalars()
    )


def create(connection, values, numbers, now):
    result = connection.execute(
        insert(groups).values(
            **{"initial_declaration_nos": numbers, **values}, created_at=now, updated_at=now
        )
    )
    group_id = result.inserted_primary_key[0]
    if numbers:
        connection.execute(
            insert(items),
            [dict(group_id=group_id, declaration_no=number, created_at=now) for number in numbers],
        )
    return group_id


def rename(connection, group_id, group_no):
    connection.execute(update(groups).where(groups.c.id == group_id).values(group_no=group_no))


def adopt_documents(connection, group_id, numbers, now):
    # 不复制或删文件；历史单票合同保留，因资料范围变化而提示重新生成。
    for table in (bills, contracts):
        connection.execute(
            update(table)
            .where(table.c.direct_declaration_no.in_(numbers))
            .values(
                direct_declaration_no=None,
                document_group_id=group_id,
                updated_at=now,
            )
        )


def resolve(connection, group_id):
    """只读追溯后继；旧链接仍能查看合并后的资料。"""
    visited = set()
    while group_id not in visited:
        visited.add(group_id)
        row = get(connection, group_id)
        if row is None or row["merged_into_id"] is None:
            return row
        group_id = row["merged_into_id"]
    return None


def member_counts(connection, group_ids):
    if not group_ids:
        return {}
    query = (
        select(items.c.group_id, func.count())
        .where(items.c.group_id.in_(group_ids))
        .group_by(items.c.group_id)
    )
    return dict(connection.execute(query).all())


def move_single_groups(connection, target_id, source_ids, now, owner):
    """调用方已校验这些组各仅一票；保留旧组头与所有文件记录。"""
    for source_id in source_ids:
        source = get(connection, source_id)
        original = source["initial_declaration_nos"] or numbers(connection, source_id)
        connection.execute(
            update(groups)
            .where(groups.c.id == source_id)
            .values(
                initial_declaration_nos=original,
                merged_into_id=target_id,
                merged_at=now,
                merged_by=owner,
                updated_at=now,
            )
        )
    if source_ids:
        connection.execute(update(items).where(items.c.group_id.in_(source_ids)).values(group_id=target_id))
        connection.execute(
            update(bills)
            .where(bills.c.document_group_id.in_(source_ids))
            .values(document_group_id=target_id, updated_at=now)
        )
        # 合并后需按新范围生成。清空稳定键可保留不同单票的同号旧合同，避免唯一键冲突。
        connection.execute(
            update(contracts)
            .where(contracts.c.document_group_id.in_(source_ids))
            .values(document_group_id=target_id, document_key=None, updated_at=now)
        )


def share_bill(connection, bill_id, numbers, now, owner):
    connection.execute(
        update(bills)
        .where(bills.c.id == bill_id)
        .values(declaration_nos=numbers, confirmed_by=owner, updated_at=now)
    )


def numbers_by_groups(connection, group_ids):
    result = {group_id: [] for group_id in group_ids}
    if group_ids:
        for row in connection.execute(
            select(items.c.group_id, items.c.declaration_no)
            .where(items.c.group_id.in_(group_ids))
            .order_by(items.c.id)
        ):
            result[row.group_id].append(row.declaration_no)
    return result


def update_basis(connection, group_id, consignee, currency, history, now):
    connection.execute(
        update(groups)
        .where(groups.c.id == group_id)
        .values(consignee=consignee, currency=currency, basis_history=history, updated_at=now)
    )
