"""发票票头：去重查询、新增、列表、详情与加锁。"""

from sqlalchemy import case, func, insert, or_, select

from ..entity import headers, items, raw_records


def by_keys(connection, account, keys):
    """已有发票及其原始数据摘要，按 invoice_key 返回。"""
    if not keys:
        return {}
    query = (
        select(
            headers.c.id,
            headers.c.invoice_key,
            headers.c.source,
            headers.c.business_type,
            headers.c.current_version_id,
            headers.c.detail_status,
            raw_records.c.payload_sha256,
        )
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
    if query.account:
        conditions.append(headers.c.lemon_account == query.account)
    keyword = query.q.strip()
    if keyword:
        conditions.append(
            or_(
                headers.c.invoice_no.contains(keyword, autoescape=True),
                headers.c.seller_name.contains(keyword, autoescape=True),
                headers.c.seller_tax_no.contains(keyword, autoescape=True),
            )
        )
    if query.status == "red_letter":
        conditions.extend(
            [headers.c.status.in_(("normal", "red_offset")), headers.c.amount_including_tax < 0]
        )
    elif query.status:
        conditions.append(headers.c.status == query.status)
        if query.status in ("normal", "red_offset"):
            conditions.append(
                or_(headers.c.amount_including_tax >= 0, headers.c.amount_including_tax.is_(None))
            )
    if query.date_from:
        conditions.append(headers.c.invoice_date >= query.date_from)
    if query.date_to:
        conditions.append(headers.c.invoice_date <= query.date_to)
    return conditions


def ids_between(connection, start, end):
    """开票日期在 start—end（含）之间的发票 ID。"""
    query = select(headers.c.id).where(headers.c.invoice_date >= start, headers.c.invoice_date <= end)
    return list(connection.execute(query).scalars())


def accounts(connection):
    """读取全部已入库账套，不受当前页或列表筛选影响。"""
    return list(
        connection.scalars(select(headers.c.lemon_account).distinct().order_by(headers.c.lemon_account))
    )


def amounts(connection, query):
    result = connection.execute(
        select(
            headers.c.currency,
            func.count().label("count"),
            func.sum(headers.c.amount_excluding_tax).label("net"),
            func.sum(headers.c.tax_amount).label("tax"),
            func.sum(headers.c.amount_including_tax).label("gross"),
        )
        .where(*_conditions(query))
        .group_by(headers.c.currency)
        .order_by(headers.c.currency)
    ).mappings()
    return [dict(row) for row in result]


def status_counts(connection, query):
    """当前筛选下按 (来源状态, 是否负金额) 计数；红字票按负金额识别，由策略归类。"""
    negative = case((headers.c.amount_including_tax < 0, True), else_=False).label("negative")
    result = connection.execute(
        select(headers.c.status, negative, func.count().label("count"))
        .where(*_conditions(query))
        .group_by(headers.c.status, negative)
    ).mappings()
    return [dict(row) for row in result]


# 人民币价税合计（当前柠檬云发票均为人民币；其他币种不混入合计，另行计数）
CNY_GROSS = func.sum(case((headers.c.currency == "CNY", headers.c.amount_including_tax), else_=None)).label(
    "gross"
)


def account_counts(connection, query):
    result = connection.execute(
        select(headers.c.lemon_account.label("account"), func.count().label("count"), CNY_GROSS)
        .where(*_conditions(query))
        .group_by(headers.c.lemon_account)
        .order_by(func.count().desc(), headers.c.lemon_account)
    ).mappings()
    return [dict(row) for row in result]


def other_currency_count(connection, query):
    """当前筛选下非人民币发票张数（不计入人民币金额图）。"""
    return connection.scalar(
        select(func.count()).select_from(headers).where(*_conditions(query), headers.c.currency != "CNY")
    )


def date_counts(connection, query):
    """当前筛选下按开票日期计数（月份在服务层汇总，避免依赖数据库日期函数）。"""
    result = connection.execute(
        select(headers.c.invoice_date.label("date"), func.count().label("count"), CNY_GROSS)
        .where(*_conditions(query), headers.c.invoice_date.is_not(None))
        .group_by(headers.c.invoice_date)
    ).mappings()
    return [dict(row) for row in result]


def amount_page(connection, query, after_id, limit):
    """统计范围按主键分批读取，只返回匹配汇总需要的票头字段。"""
    result = connection.execute(
        select(
            headers.c.id,
            headers.c.currency,
            headers.c.status,
            headers.c.detail_status,
            headers.c.current_version_id,
            headers.c.amount_including_tax,
        )
        .where(*_conditions(query), headers.c.id > after_id)
        .order_by(headers.c.id)
        .limit(limit)
    ).mappings()
    return [dict(row) for row in result]


def page(connection, query):
    """返回 (总数, 按币种汇总, 本页票头含明细行数)；同日期按主键倒序稳定分页。"""
    conditions = _conditions(query)
    total = connection.scalar(select(func.count()).select_from(headers).where(*conditions))
    totals = amounts(connection, query)
    line_count = (
        select(func.count())
        .select_from(items)
        .where(items.c.invoice_id == headers.c.id, items.c.is_active.is_(True))
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
    return total, totals, [dict(row) for row in rows]


def by_ids(connection, invoice_ids, *, lock=False):
    if not invoice_ids:
        return []
    query = select(headers).where(headers.c.id.in_(invoice_ids)).order_by(headers.c.id)
    if lock:
        query = query.with_for_update()
    return [dict(row) for row in connection.execute(query).mappings()]


def by_numbers(connection, numbers):
    """发票号码精确命中的票头（含作废、红冲），供人工上传发票文件时识别归属。"""
    if not numbers:
        return []
    query = (
        select(headers.c.id, headers.c.invoice_no, headers.c.status, headers.c.seller_name)
        .where(headers.c.invoice_no.in_(sorted(set(numbers))))
        .order_by(headers.c.id)
    )
    return [dict(row) for row in connection.execute(query).mappings()]
