"""银行收汇明细读取；不提交事务、不判断回款路径。

本文件只有读取：收汇记录由表格导入写入，导入用例尚未实现（见模块 README“尚未实现”）。
"""

from sqlalchemy import case, func, select

from ..entity.bank_receipt import settlement_bank_receipts as receipts


def _conditions(filters):
    conditions = []
    if filters.get("customer"):
        conditions.append(receipts.c.customer_name.contains(filters["customer"], autoescape=True))
    if filters.get("receiving_company"):
        conditions.append(
            receipts.c.receiving_company.contains(filters["receiving_company"], autoescape=True)
        )
    if filters.get("date_from"):
        conditions.append(receipts.c.receipt_date >= filters["date_from"])
    if filters.get("date_to"):
        conditions.append(receipts.c.receipt_date <= filters["date_to"])
    if filters.get("third_party") is True:
        conditions.append(receipts.c.payer_key != receipts.c.customer_key)
    elif filters.get("third_party") is False:
        conditions.append(receipts.c.payer_key == receipts.c.customer_key)
    return conditions


def page(connection, filters, offset, limit):
    """按收汇日期倒序分页：返回 (总笔数, 当前页)。"""
    conditions = _conditions(filters)
    total = connection.execute(select(func.count()).select_from(receipts).where(*conditions)).scalar_one()
    query = (
        select(receipts)
        .where(*conditions)
        .order_by(receipts.c.receipt_date.desc(), receipts.c.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return total, [dict(row) for row in connection.execute(query).mappings()]


def totals(connection, filters):
    """筛选范围内按收汇抬头与币种汇总：[{receiving_company, currency, count, amount,
    third_party_count, third_party_amount}]。"""
    third_party = receipts.c.payer_key != receipts.c.customer_key
    query = (
        select(
            receipts.c.receiving_company,
            receipts.c.currency,
            func.count().label("count"),
            func.sum(receipts.c.amount).label("amount"),
            func.sum(case((third_party, 1), else_=0)).label("third_party_count"),
            func.sum(case((third_party, receipts.c.amount), else_=0)).label("third_party_amount"),
        )
        .where(*_conditions(filters))
        .group_by(receipts.c.receiving_company, receipts.c.currency)
        .order_by(receipts.c.receiving_company, receipts.c.currency)
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def all_receipts(connection):
    """全部收汇记录，按收汇日期、主键升序；直接收汇明细逐笔累计余额用。"""
    query = select(receipts).order_by(receipts.c.receipt_date, receipts.c.id)
    return [dict(row) for row in connection.execute(query).mappings()]
