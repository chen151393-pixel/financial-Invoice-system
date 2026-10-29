"""任务和整票指针存取；调用方管理事务和状态。"""

from sqlalchemy import func, or_, select

from ..entity import invoice_guards, tasks


def get(connection, task_id):
    row = connection.execute(select(tasks).where(tasks.c.id == task_id).with_for_update()).mappings().first()
    return dict(row) if row else None


def current(connection, invoice_id):
    row = (
        connection.execute(
            select(tasks)
            .join(invoice_guards, invoice_guards.c.task_id == tasks.c.id)
            .where(invoice_guards.c.invoice_id == invoice_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def by_snapshot(connection, invoice_id, fingerprint):
    row = (
        connection.execute(
            select(tasks).where(tasks.c.invoice_id == invoice_id, tasks.c.fingerprint == fingerprint)
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def add(connection, values, stamp):
    task_id = connection.execute(
        tasks.insert().values(**values, created_at=stamp, updated_at=stamp)
    ).inserted_primary_key[0]
    existing = connection.execute(
        select(invoice_guards.c.id).where(invoice_guards.c.invoice_id == values["invoice_id"])
    ).scalar()
    if existing:
        connection.execute(
            invoice_guards.update()
            .where(invoice_guards.c.id == existing)
            .values(task_id=task_id, updated_at=stamp)
        )
    else:
        connection.execute(
            invoice_guards.insert().values(
                invoice_id=values["invoice_id"], task_id=task_id, created_at=stamp, updated_at=stamp
            )
        )
    return task_id


def change(connection, task_id, values, stamp):
    connection.execute(tasks.update().where(tasks.c.id == task_id).values(**values, updated_at=stamp))


def keyword_clauses(keyword):
    if not keyword:
        return []
    return [
        or_(
            *(
                col.contains(keyword, autoescape=True)
                for col in (tasks.c.task_no, tasks.c.invoice_no, tasks.c.vendor_name)
            )
        )
    ]


def parent_order_matches(number, dialect):
    # 只搜索不可变审核快照的母单号，不能搜索整段 JSON 而误中候选账单、备注或子单。
    if dialect == "mysql":
        pattern = "%" + number.replace("/", "//").replace("%", "/%").replace("_", "/_") + "%"
        return func.json_search(tasks.c.snapshot, "one", pattern, "/", "$.sources.*.parent_number").is_not(
            None
        )
    sources = func.json_each(tasks.c.snapshot, "$.sources").table_valued("value", joins_implicitly=True)
    return (
        select(1)
        .select_from(sources)
        .where(func.json_extract(sources.c.value, "$.parent_number").contains(number, autoescape=True))
        .correlate(tasks)
        .exists()
    )


def search_clauses(criteria, dialect):
    clauses = keyword_clauses(criteria.keyword)
    for field, column in (
        (criteria.taskNo, tasks.c.task_no),
        (criteria.invoiceNo, tasks.c.invoice_no),
        (criteria.supplierName, tasks.c.vendor_name),
    ):
        if field.strip():
            clauses.append(column.contains(field.strip(), autoescape=True))
    if criteria.parentOrderNo.strip():
        clauses.append(parent_order_matches(criteria.parentOrderNo.strip(), dialect))
    return clauses


def counts_by_state(connection, criteria):
    # 概况与列表采用相同组合条件；概况不受状态和分页限制。
    return dict(
        connection.execute(
            select(tasks.c.state, func.count())
            .where(*search_clauses(criteria, connection.dialect.name))
            .group_by(tasks.c.state)
        ).all()
    )


def page(connection, criteria, states=None):
    # 本地队列跨连接环境可见；任务原有来源身份和执行校验保持不变。
    clauses = search_clauses(criteria, connection.dialect.name)
    if criteria.state:
        clauses.append(tasks.c.state == criteria.state)
    if states is not None:
        clauses.append(tasks.c.state.in_(states))
    total = connection.execute(select(func.count()).select_from(tasks).where(*clauses)).scalar_one()
    rows = connection.execute(
        select(tasks)
        .where(*clauses)
        .order_by(tasks.c.id.desc())
        .offset((criteria.page - 1) * criteria.pageSize)
        .limit(criteria.pageSize)
    ).mappings()
    return [dict(row) for row in rows], total


def pending(connection, stamp):
    return list(
        connection.execute(
            select(tasks.c.id, tasks.c.revision)
            .where(
                tasks.c.state.in_(["queued", "waiting_bill"]),
                or_(tasks.c.next_query_at.is_(None), tasks.c.next_query_at <= stamp),
                or_(tasks.c.lease_until.is_(None), tasks.c.lease_until <= stamp),
            )
            .order_by(tasks.c.id)
            .limit(4)
        ).mappings()
    )


def ready_to_write(connection):
    return list(
        connection.execute(
            select(tasks.c.id, tasks.c.revision, tasks.c.vendor_id)
            .where(tasks.c.state == "ready")
            .order_by(tasks.c.id)
            .limit(4)
        ).mappings()
    )
