"""开票任务：新增、加锁读取、状态更新与列表查询。"""

from sqlalchemy import desc, func, insert, or_, select, update

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


def set_status(connection, task_id, status, now, *, completed_at=None):
    connection.execute(
        update(tasks)
        .where(tasks.c.id == task_id)
        .values(status=status, completed_at=completed_at, updated_at=now)
    )


def conditions(*, scope, account, keyword, supplier_ids, order_ids):
    """scope：current（未被替代）/ superseded / all；关键字匹配 CD 编号、供应商或子采购单。"""
    result = []
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


def accounts(connection):
    query = select(tasks.c.ns_account).distinct().order_by(tasks.c.ns_account)
    return list(connection.execute(query).scalars())
