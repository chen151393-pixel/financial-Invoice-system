"""按票面日期汇总已导入的正常进项票，币种分别计量。"""

from sqlalchemy import case, func, select

from ..entity import headers


def daily(connection, start, end):
    query = (
        select(
            headers.c.invoice_date.label("date"),
            headers.c.currency,
            case(
                (
                    func.count(headers.c.amount_including_tax) == func.count(),
                    func.sum(headers.c.amount_including_tax),
                ),
                else_=None,
            ).label("amount"),
        )
        .where(
            headers.c.status == "normal",
            headers.c.invoice_date >= start,
            headers.c.invoice_date <= end,
        )
        .group_by(headers.c.invoice_date, headers.c.currency)
        .order_by(headers.c.invoice_date)
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def latest_date(connection):
    return connection.scalar(select(func.max(headers.c.invoice_date)).where(headers.c.status == "normal"))
