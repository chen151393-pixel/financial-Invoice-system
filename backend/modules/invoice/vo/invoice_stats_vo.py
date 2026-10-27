"""进项发票分布统计响应：按月、票面状态、柠檬云账套计数（随列表筛选条件变化）。"""

from backend.core.dto import StrictModel


class MonthCount(StrictModel):
    month: str
    count: int


class StatusCount(StrictModel):
    key: str
    label: str
    count: int


class AccountCount(StrictModel):
    account: str
    count: int


class InvoiceStats(StrictModel):
    total: int
    months: list[MonthCount]
    statuses: list[StatusCount]
    accounts: list[AccountCount]
