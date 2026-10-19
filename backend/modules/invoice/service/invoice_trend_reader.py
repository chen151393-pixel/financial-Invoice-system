"""工作台已开票趋势的只读门面；未导入的外部发票不在统计范围。"""

from ..dao import invoice_trend_dao


def invoice_daily_amounts(connection, start, end):
    return invoice_trend_dao.daily(connection, start, end)


def latest_invoice_date(connection):
    return invoice_trend_dao.latest_date(connection)
