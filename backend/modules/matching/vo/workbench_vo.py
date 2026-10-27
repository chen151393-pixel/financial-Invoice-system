"""工作台响应：待办金额不跨业务相加；图表几何值由后端返回。"""

from typing import Literal

from pydantic import Field

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
    # 业务状态：核对待办为待审批，比对待办为待核票，开票待办按任务状态归类
    stage: str = ""
    stageLabel: str = ""
    reason: str
    createdAt: str
    priority: int
    attention: bool = False


class WorkbenchCounts(StrictModel):
    all: int = 0
    review: int = 0
    matching: int = 0
    task: int = 0
    reverify: int = 0
    preparation: int = 0


class StageCount(StrictModel):
    """业务状态分区：按报关单计数（报关单下当前任务中最慢的阶段）。"""

    key: Literal["pending_review", "notify", "invoicing", "documents", "completed"]
    label: str
    count: int


class SupplierOption(StrictModel):
    id: str
    name: str


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


class FunnelStep(StrictModel):
    key: str
    label: str
    count: int
    # 相对上一步的通过率（百分比字符串）；第一步或上一步为 0 时为空
    rate: str | None


class MonthlyReceipt(StrictModel):
    month: str
    currency: str
    expected: str
    received: str
    percent: str | None
    # 当月应开金额缺失、未计入的任务数
    unknownTasks: int


class QueueTiers(StrictModel):
    all: int
    high: int
    medium: int
    low: int


class Workbench(StrictModel):
    generatedAt: str
    accounts: list[str]
    counts: WorkbenchCounts
    filteredCounts: WorkbenchCounts
    stages: list[StageCount] = Field(default_factory=list)
    # 审核通过但没有开票任务（供应商均关闭通知）的报关单，不进分区与待办
    noTaskCount: int = 0
    # 供应商筛选选项（有效报关单关联的供应商）；suppliers 为待收票排名
    supplierOptions: list[SupplierOption] = Field(default_factory=list)
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
    # 业务流程漏斗（由五个业务状态累加）、按任务生成月份的人民币应开与已收、待审核比对建议的置信度分档
    funnel: list[FunnelStep] = Field(default_factory=list)
    monthly: list[MonthlyReceipt] = Field(default_factory=list)
    queue: QueueTiers | None = None


class WorkbenchExport(StrictModel):
    filename: str
    content: str
    count: int
