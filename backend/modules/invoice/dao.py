"""发票SQL和账户命名锁；不提交事务、不决定重复或冲突业务状态。"""

from sqlalchemy import func, or_, select, text


def invoice_list(connection, head, lines, tenant, query):
    conditions = [head.c.tenant_id == tenant, head.c.is_active == 1, head.c.invoice_direction == "input"]
    if query.q.strip():
        conditions.append(
            or_(
                head.c.invoice_no.contains(query.q.strip(), autoescape=True),
                head.c.seller_name.contains(query.q.strip(), autoescape=True),
                head.c.seller_tax_no.contains(query.q.strip(), autoescape=True),
            )
        )
    if query.status:
        conditions.append(head.c.invoice_status == query.status)
    if query.date_from:
        conditions.append(head.c.invoice_date >= query.date_from)
    if query.date_to:
        conditions.append(head.c.invoice_date <= query.date_to)
    total = connection.scalar(select(func.count()).select_from(head).where(*conditions))
    amounts = (
        connection.execute(
            select(
                head.c.currency_code,
                func.count().label("count"),
                func.sum(head.c.amount_excluding_tax).label("net"),
                func.sum(head.c.tax_amount).label("tax"),
                func.sum(head.c.amount_including_tax).label("gross"),
            )
            .where(*conditions)
            .group_by(head.c.currency_code)
            .order_by(head.c.currency_code)
        )
        .mappings()
        .all()
    )
    counts = (
        select(func.count())
        .select_from(lines)
        .where(lines.c.tenant_id == tenant, lines.c.invoice_id == head.c.id, lines.c.is_active == 1)
        .correlate(head)
        .scalar_subquery()
    )
    # 列表不加载来源JSON，明细只在用户展开时读取。
    columns = [
        head.c[name]
        for name in (
            "id",
            "invoice_no",
            "invoice_date",
            "seller_name",
            "seller_tax_no",
            "invoice_type_name",
            "business_type_name",
            "invoice_status",
            "invoice_status_raw",
            "validation_status",
            "currency_code",
            "amount_excluding_tax",
            "tax_amount",
            "amount_including_tax",
            "synced_at",
            "external_system",
        )
    ]
    records = (
        connection.execute(
            select(*columns, counts.label("line_count"))
            .where(*conditions)
            .order_by(head.c.invoice_date.desc(), head.c.id.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        .mappings()
        .all()
    )
    return total, amounts, records


def lock_invoice(connection, head, tenant, invoice_id):
    connection.execute(
        select(head.c.id).where(head.c.id == invoice_id, head.c.tenant_id == tenant).with_for_update()
    ).all()


def invoice_detail(connection, head, lines, tenant, invoice_id):
    record = (
        connection.execute(
            select(head).where(
                head.c.id == invoice_id,
                head.c.tenant_id == tenant,
                head.c.is_active == 1,
                head.c.invoice_direction == "input",
            )
        )
        .mappings()
        .first()
    )
    if record is None:
        return None, []
    details = (
        connection.execute(
            select(lines)
            .where(lines.c.invoice_id == invoice_id, lines.c.tenant_id == tenant, lines.c.is_active == 1)
            .order_by(lines.c.id)
        )
        .mappings()
        .all()
    )
    return record, details


def invoice_details(connection, head, lines, tenant, invoice_ids):
    records = (
        connection.execute(
            select(head).where(
                head.c.id.in_(invoice_ids),
                head.c.tenant_id == tenant,
                head.c.is_active == 1,
                head.c.invoice_direction == "input",
            )
        )
        .mappings()
        .all()
    )
    details = (
        connection.execute(
            select(lines)
            .where(
                lines.c.invoice_id.in_([row["id"] for row in records]),
                lines.c.tenant_id == tenant,
                lines.c.is_active == 1,
            )
            .order_by(lines.c.id)
        )
        .mappings()
        .all()
    )
    return records, details


def lock(connection, name):
    return connection.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": name}).scalar() == 1


def unlock(connection, name):
    connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})


def existing(connection, head, tenant, numbers):
    return (
        connection.execute(
            select(
                head.c.id,
                head.c.invoice_no,
                head.c.content_hash,
                head.c.external_system,
                head.c.external_account,
                head.c.import_key,
            )
            .where(head.c.tenant_id == tenant, head.c.invoice_no.in_(numbers))
            .with_for_update()
        )
        .mappings()
        .all()
    )


def insert(connection, head_table, line_table, head, lines):
    invoice_id = connection.execute(head_table.insert().values(**head)).inserted_primary_key[0]
    connection.execute(line_table.insert(), [{**line, "invoice_id": invoice_id} for line in lines])
    return invoice_id
