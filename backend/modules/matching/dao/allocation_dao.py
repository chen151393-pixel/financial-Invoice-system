"""比对与分配记录：新增、加锁读取、状态更新、汇总与审核队列。"""

from sqlalchemy import case, false, func, insert, select, update

from ..entity import allocations

ACTIVE = ("proposed", "confirmed")


def insert_allocation(connection, values, now):
    return connection.execute(
        insert(allocations).values(created_at=now, updated_at=now, **values)
    ).inserted_primary_key[0]


def get(connection, allocation_id, *, lock=False):
    query = select(allocations).where(allocations.c.id == allocation_id)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def by_request(connection, request_id):
    row = (
        connection.execute(select(allocations).where(allocations.c.request_id == request_id))
        .mappings()
        .first()
    )
    return dict(row) if row else None


def update_status(connection, allocation_id, values, now):
    connection.execute(
        update(allocations).where(allocations.c.id == allocation_id).values(updated_at=now, **values)
    )


def by_invoices(connection, invoice_ids):
    if not invoice_ids:
        return []
    query = (
        select(allocations)
        .where(allocations.c.invoice_id.in_(invoice_ids))
        .order_by(allocations.c.invoice_item_id, allocations.c.id)
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def confirmed_for_totals(connection, invoice_ids):
    """只取已确认分配的金额与版本依据，不把建议、驳回或取消计入。"""
    if not invoice_ids:
        return []
    fields = (
        "invoice_id",
        "amount",
        "verification_status",
        "invoice_version_id",
        "purchase_line_id",
        "purchase_basis_id",
        "verification_history",
    )
    result = connection.execute(
        select(*(allocations.c[key] for key in fields)).where(
            allocations.c.invoice_id.in_(invoice_ids), allocations.c.status == "confirmed"
        )
    ).mappings()
    return [dict(row) for row in result]


def active_item_ids(connection, item_ids):
    """已有待审核建议或已通过分配的发票行。"""
    if not item_ids:
        return set()
    query = select(allocations.c.invoice_item_id).where(
        allocations.c.invoice_item_id.in_(item_ids), allocations.c.status.in_(ACTIVE)
    )
    return set(connection.execute(query).scalars())


def confirmed_by_item(connection, item_id, *, exclude_id=None):
    """发票行已通过分配的数量、金额合计。

    使用锁定读：MySQL 可重复读下普通查询读到事务开始时的快照，会漏掉并发提交的分配而超用发票行。
    """
    query = select(
        func.coalesce(func.sum(allocations.c.quantity), 0), func.coalesce(func.sum(allocations.c.amount), 0)
    ).where(allocations.c.invoice_item_id == item_id, allocations.c.status == "confirmed")
    if exclude_id is not None:
        query = query.where(allocations.c.id != exclude_id)
    return tuple(connection.execute(query.with_for_update()).one())


def confirmed_by_purchase_lines(connection, purchase_line_ids):
    """{子采购行: (已通过数量, 已通过金额, 是否人工确认已开完)}；锁定读，避免并发通过时丢失更新。"""
    if not purchase_line_ids:
        return {}
    query = (
        select(
            allocations.c.purchase_line_id,
            func.sum(allocations.c.quantity),
            func.sum(allocations.c.amount),
            func.max(case((allocations.c.closes_purchase_line, 1), else_=0)),
        )
        .where(allocations.c.purchase_line_id.in_(purchase_line_ids), allocations.c.status == "confirmed")
        .group_by(allocations.c.purchase_line_id)
        .with_for_update()
    )
    return {row[0]: (row[1], row[2], bool(row[3])) for row in connection.execute(query)}


def _scope(line_ids, invoice_ids):
    """供应商、开票日期筛选：调用方经门面预先算出子采购行 / 发票 ID；None 为不限，空集合无结果。"""
    where = []
    for column, ids in ((allocations.c.purchase_line_id, line_ids), (allocations.c.invoice_id, invoice_ids)):
        if ids is not None:
            where.append(column.in_(sorted(ids)) if ids else false())
    return where


def queue(connection, *, tiers, offset, limit, line_ids=None, invoice_ids=None):
    """待审核建议，置信度高的在前；tiers 为置信度下限与上限 (low, high)，None 表示不限。"""
    where = [allocations.c.status == "proposed", *_scope(line_ids, invoice_ids)]
    low, high = tiers
    if low is not None:
        where.append(allocations.c.confidence >= low)
    if high is not None:
        where.append(allocations.c.confidence < high)
    total = connection.execute(select(func.count()).select_from(allocations).where(*where)).scalar()
    query = (
        select(allocations)
        .where(*where)
        .order_by(allocations.c.confidence.desc(), allocations.c.id)
        .offset(offset)
        .limit(limit)
    )
    return total, [dict(row) for row in connection.execute(query).mappings()]


def proposed_line_ids(connection):
    """待审核建议涉及的子采购行，供生成供应商筛选选项。"""
    query = select(allocations.c.purchase_line_id).distinct().where(allocations.c.status == "proposed")
    return list(connection.execute(query).scalars())


def proposal_counts(connection, high, medium, *, line_ids=None, invoice_ids=None):
    """待审核建议按置信度分档计数（高 >= high，中 >= medium，其余为低）。"""
    confidence = allocations.c.confidence
    query = select(
        func.count(),
        func.sum(case((confidence >= high, 1), else_=0)),
        func.sum(case(((confidence >= medium) & (confidence < high), 1), else_=0)),
    ).where(allocations.c.status == "proposed", *_scope(line_ids, invoice_ids))
    # MySQL 的 SUM(CASE ...) 返回 Decimal；计数统一为整数，避免严格响应模型校验失败。
    total, high_count, medium_count = (int(value or 0) for value in connection.execute(query).one())
    return {
        "all": total,
        "high": high_count,
        "medium": medium_count,
        "low": total - high_count - medium_count,
    }
