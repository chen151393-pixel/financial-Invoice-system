"""工作台响应：待办金额不跨业务相加；图表几何值由后端返回。"""

from typing import Literal

from backend.core.dto import StrictModel


class Todo(StrictModel):
    key: str
    kind: Literal["review", "matching", "task"]
    targetId: str
    title: str
    subtitle: str
    party: str
    account: str
    amount: str | None
    currency: str
    amountLabel: str
    statusLabel: str
    reason: str
    createdAt: str
    priority: int
    attention: bool = False


class WorkbenchCounts(StrictModel):
    all: int = 0
    review: int = 0
    matching: int = 0
    task: int = 0
    unshipped: int = 0  # 未出库报关单数，不计入待办
    reverify: int = 0
    preparation: int = 0


class CurrencyAmount(StrictModel):
    currency: str
    amount: str | None


class MonthProgress(StrictModel):
    month: str
    total: int
    completed: int
    percent: str | None
    received: list[CurrencyAmount]


class SupplierRank(StrictModel):
    key: str
    supplier: str
    account: str
    currency: str
    amount: str
    percent: str


class TrendPoint(StrictModel):
    date: str
    amount: str | None
    percent: str
    negative: bool


class InvoiceTrend(StrictModel):
    currency: str
    hasNegative: bool
    points: list[TrendPoint]


class Workbench(StrictModel):
    generatedAt: str
    accounts: list[str]
    counts: WorkbenchCounts
    filteredCounts: WorkbenchCounts
    items: list[Todo]
    total: int
    page: int
    pageSize: int
    pages: int
    month: MonthProgress
    suppliers: list[SupplierRank]
    unknownSupplierAmounts: int
    trendStart: str
    trendEnd: str
    latestInvoiceDate: str | None
    trend: list[InvoiceTrend]


class WorkbenchExport(StrictModel):
    filename: str
    content: str
    count: int
