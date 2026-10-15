"""发票票头：去重查询、新增、列表、详情与加锁。"""

from sqlalchemy import func, insert, or_, select

from ..entity import headers, items, raw_records


def by_keys(connection, account, keys):
    """已有发票及其原始数据摘要，按 invoice_key 返回。"""
    if not keys:
        return {}
    query = (
        select(headers.c.id, headers.c.invoice_key, headers.c.source, raw_records.c.payload_sha256)
        .select_from(headers.outerjoin(raw_records, raw_records.c.id == headers.c.raw_record_id))
        .where(headers.c.lemon_account == account, headers.c.invoice_key.in_(keys))
    )
    return {row["invoice_key"]: dict(row) for row in connection.execute(query).mappings()}


def insert_header(connection, values, now):
    return connection.execute(
        insert(headers).values(created_at=now, updated_at=now, **values)
    ).inserted_primary_key[0]


def _conditions(query):
    conditions = []
    keyword = query.q.strip()
    if keyword:
        conditions.append(
            or_(
                headers.c.invoice_no.contains(keyword, autoescape=True),
                headers.c.seller_name.contains(keyword, autoescape=True),
                headers.c.seller_tax_no.contains(keyword, autoescape=True),
            )
        )
    if query.status:
        conditions.append(headers.c.status == query.status)
    if query.date_from:
        conditions.append(headers.c.invoice_date >= query.date_from)
    if query.date_to:
        conditions.append(headers.c.invoice_date <= query.date_to)
    return conditions


def page(connection, query):
    """返回 (总数, 按币种汇总, 本页票头含明细行数)；同日期按主键倒序稳定分页。"""
    conditions = _conditions(query)
    total = connection.scalar(select(func.count()).select_from(headers).where(*conditions))
    amounts = connection.execute(
        select(
            headers.c.currency,
            func.count().label("count"),
            func.sum(headers.c.amount_excluding_tax).label("net"),
            func.sum(headers.c.tax_amount).label("tax"),
            func.sum(headers.c.amount_including_tax).label("gross"),
        )
        .where(*conditions)
        .group_by(headers.c.currency)
        .order_by(headers.c.currency)
    ).mappings()
    line_count = (
        select(func.count())
        .select_from(items)
        .where(items.c.invoice_id == headers.c.id)
        .correlate(headers)
        .scalar_subquery()
    )
    rows = connection.execute(
        select(headers, line_count.label("line_count"))
        .where(*conditions)
        .order_by(headers.c.invoice_date.desc(), headers.c.id.desc())
        .offset((query.page - 1) * query.page_size)
        .limit(query.page_size)
    ).mappings()
    return total, [dict(row) for row in amounts], [dict(row) for row in rows]


def by_ids(connection, invoice_ids, *, lock=False):
    if not invoice_ids:
        return []
    query = select(headers).where(headers.c.id.in_(invoice_ids)).order_by(headers.c.id)
    if lock:
        query = query.with_for_update()
    return [dict(row) for row in connection.execute(query).mappings()]
