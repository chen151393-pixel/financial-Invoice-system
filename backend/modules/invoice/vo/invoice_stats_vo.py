"""进项发票分布统计响应：按月、票面状态、柠檬云账套计数（随列表筛选条件变化）。"""

from backend.core.dto import StrictModel


class MonthCount(StrictModel):
    month: str
    count: int
    # 人民币价税合计（十进制字符串）；当月无人民币发票为 "0.00"
    gross: str


class StatusCount(StrictModel):
    key: str
    label: str
    count: int


class AccountCount(StrictModel):
    account: str
    count: int
    gross: str


class InvoiceStats(StrictModel):
    total: int
    # 非人民币发票张数：金额图只统计人民币，有其他币种时页面提示
    otherCurrencyCount: int
    months: list[MonthCount]
    statuses: list[StatusCount]
    accounts: list[AccountCount]
