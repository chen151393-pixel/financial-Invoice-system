"""开票任务：新增、加锁读取、状态更新与列表查询。"""

from sqlalchemy import desc, false, func, insert, or_, select, update

from ..entity import task_lines, tasks

GROUP_COLUMNS = {"supplier": tasks.c.supplier_id, "declaration": tasks.c.customs_declaration_id}


def insert_task(connection, values, now):
    return connection.execute(
        insert(tasks).values(created_at=now, updated_at=now, **values)
    ).inserted_primary_key[0]


def get(connection, task_id, *, lock=False):
    query = select(tasks).where(tasks.c.id == task_id)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def by_review(connection, review_id, *, lock=False):
    query = select(tasks).where(tasks.c.review_id == review_id).order_by(tasks.c.id)
    if lock:
        query = query.with_for_update()
    return [dict(row) for row in connection.execute(query).mappings()]


def current_ids_by_declaration(connection, declaration_id):
    """报关单下未被替代的任务 ID（资料到齐后据此重算完结）。"""
    query = select(tasks.c.id).where(
        tasks.c.customs_declaration_id == declaration_id, tasks.c.status != "superseded"
    )
    return sorted(connection.execute(query).scalars())


def current_ids_by_orders(connection, order_ids):
    """含这些子采购单任务行的未被替代任务 ID。"""
    if not order_ids:
        return []
    query = (
        select(tasks.c.id)
        .distinct()
        .join(task_lines, task_lines.c.task_id == tasks.c.id)
        .where(task_lines.c.purchase_order_id.in_(order_ids), tasks.c.status != "superseded")
    )
    return sorted(connection.execute(query).scalars())


def set_status(connection, task_id, status, now, *, completed_at=None):
    connection.execute(
        update(tasks)
        .where(tasks.c.id == task_id)
        .values(status=status, completed_at=completed_at, updated_at=now)
    )


def conditions(*, scope, account, keyword, supplier_ids, order_ids, supplier_id=None, declaration_ids=None):
    """scope：current（未被替代）/ superseded / all；关键字匹配 CD 编号、供应商或子采购单；可按供应商筛选。

    declaration_ids：业务状态、报关单创建日期等条件预先算出的报关单 ID 集合；None 为不限，空集合无结果。
    """
    result = []
    if declaration_ids is not None:
        result.append(
            tasks.c.customs_declaration_id.in_(sorted(declaration_ids)) if declaration_ids else false()
        )
    if supplier_id:
        result.append(tasks.c.supplier_id == supplier_id)
    if scope == "current":
        result.append(tasks.c.status != "superseded")
    elif scope == "superseded":
        result.append(tasks.c.status == "superseded")
    if account:
        result.append(tasks.c.ns_account == account)
    if keyword:
        matches = [tasks.c.record_no.like(f"%{keyword}%")]
        if supplier_ids:
            matches.append(tasks.c.supplier_id.in_(supplier_ids))
        if order_ids:
            matches.append(
                tasks.c.id.in_(
                    select(task_lines.c.task_id).where(task_lines.c.purchase_order_id.in_(order_ids))
                )
            )
        result.append(or_(*matches))
    return result


def group_page(connection, where, group_by, offset, limit):
    """按分组分页：返回分组总数与本页分组键（最新任务在前）；供应商为空的任务归为一组。"""
    column = GROUP_COLUMNS[group_by]
    grouped = select(column.label("key"), func.max(tasks.c.id).label("latest")).where(*where).group_by(column)
    total = connection.execute(select(func.count()).select_from(grouped.subquery())).scalar()
    keys = connection.execute(grouped.order_by(desc("latest")).offset(offset).limit(limit)).scalars()
    return total, list(keys)


def in_groups(connection, where, group_by, keys):
    if not keys:
        return []
    column = GROUP_COLUMNS[group_by]
    known = [key for key in keys if key is not None]
    matches = [column.in_(known)] if known else []
    if None in keys:
        matches.append(column.is_(None))
    query = select(tasks).where(*where, or_(*matches)).order_by(tasks.c.id.desc())
    return [dict(row) for row in connection.execute(query).mappings()]


def status_counts(connection, where):
    query = select(tasks.c.status, func.count()).where(*where).group_by(tasks.c.status)
    return {status: count for status, count in connection.execute(query)}


def declaration_statuses(connection, account):
    """{报关单 ID: [当前任务状态]}，供按业务状态（报关单下最慢的阶段）筛选。"""
    query = select(tasks.c.customs_declaration_id, tasks.c.status).where(tasks.c.status != "superseded")
    if account:
        query = query.where(tasks.c.ns_account == account)
    result = {}
    for row in connection.execute(query):
        result.setdefault(row.customs_declaration_id, []).append(row.status)
    return result


def supplier_ids(connection, account):
    """未被替代的任务涉及的供应商，供筛选下拉使用。"""
    query = (
        select(tasks.c.supplier_id)
        .distinct()
        .where(tasks.c.status != "superseded", tasks.c.supplier_id.is_not(None))
    )
    if account:
        query = query.where(tasks.c.ns_account == account)
    return list(connection.execute(query).scalars())


def accounts(connection):
    query = select(tasks.c.ns_account).distinct().order_by(tasks.c.ns_account)
    return list(connection.execute(query).scalars())


def by_ids(connection, task_ids, *, lock=False):
    if not task_ids:
        return []
    query = select(tasks).where(tasks.c.id.in_(task_ids)).order_by(tasks.c.id)
    if lock:
        query = query.with_for_update()
    return [dict(row) for row in connection.execute(query).mappings()]


def open_lines(connection, purchase_line_ids):
    """有效任务行及所属任务字段；purchase_line_ids 为 None 时返回全部未结束（open / partial）的行。"""
    query = select(
        task_lines.c.id.label("task_line_id"),
        task_lines.c.task_id,
        task_lines.c.purchase_order_id,
        task_lines.c.purchase_line_id,
        task_lines.c.purchase_basis_id,
        task_lines.c.requires_review,
        task_lines.c.ledger_sha256,
        task_lines.c.pending_quantity,
        task_lines.c.pending_amount,
        task_lines.c.expected_quantity,
        task_lines.c.unit,
        task_lines.c.expected_amount,
        task_lines.c.received_quantity,
        task_lines.c.received_amount,
        task_lines.c.status,
        tasks.c.status.label("task_status"),
        tasks.c.ns_account,
        tasks.c.record_no,
        tasks.c.customs_declaration_id,
        tasks.c.supplier_id,
        tasks.c.company_id,
        tasks.c.currency,
    ).select_from(task_lines.join(tasks, tasks.c.id == task_lines.c.task_id))
    if purchase_line_ids is None:
        query = query.where(task_lines.c.status.in_(("open", "partial")))
    else:
        query = query.where(task_lines.c.active_purchase_line_id.in_(purchase_line_ids))
    return [dict(row) for row in connection.execute(query.order_by(task_lines.c.id)).mappings()]
