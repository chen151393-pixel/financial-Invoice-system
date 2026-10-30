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
    # 处理方：财务（核对、比对）或采购（开票跟进）；waitingDays 为自入库或生成起的天数
    role: Literal["finance", "purchase"] = "finance"
    waitingDays: int | None = None


class WorkbenchCounts(StrictModel):
    all: int = 0
    review: int = 0
    matching: int = 0
    task: int = 0
    reverify: int = 0
    preparation: int = 0


class SupplierOption(StrictModel):
    id: str
    name: str


class SupplierRank(StrictModel):
    key: str
    supplier: str
    account: str
    currency: str
    amount: str
    percent: str
    # 该供应商未完成任务中最早生成的已等待天数；超过 15 天为 overdue
    longestDays: int = 0
    overdue: bool = False


class FlowPosition(StrictModel):
    """停在某一位置（待财务审核或开票跟进节点）的报关单数。"""

    key: str
    label: str
    count: int


class FunnelStep(StrictModel):
    key: str
    label: str
    count: int
    # 相对上一步的通过率（百分比字符串）；第一步或上一步为 0 时为空
    rate: str | None
    # 卡在上一步与这一步之间的报关单，按位置分项
    stuck: list[FlowPosition] = Field(default_factory=list)


class Funnel(StrictModel):
    steps: list[FunnelStep]
    # 整体完结率：完结 / 第一步；第一步为 0 时为空
    completionRate: str | None


class NodeShare(StrictModel):
    key: str
    label: str
    count: int
    percent: str


class NodeDistribution(StrictModel):
    total: int
    nodes: list[NodeShare]


class Kpi(StrictModel):
    """关键指标：value 为十进制字符串（金额）或整数文本；series 为近 6 个月序列，只用于画走势线。"""

    key: str
    label: str
    role: Literal["finance", "purchase"]
    value: str
    unit: str
    currency: str
    delta: str
    direction: Literal["up", "down", "flat"]
    tone: Literal["positive", "warning", "neutral"]
    hint: str
    series: list[str]


class MonthlyReceipt(StrictModel):
    month: str
    currency: str
    expected: str
    received: str
    invoiceCount: int
    percent: str | None
    # 保留旧字段名兼容调用方；现为当月合计金额缺失、未计入的去重子采购单数。
    unknownTasks: int
    orderCount: int = 0


class AnomalyCount(StrictModel):
    label: str
    count: int
    # 相对最多一类的条长（0–100）
    percent: str


class QueueTiers(StrictModel):
    all: int
    high: int
    medium: int
    low: int
    # 待审核建议中比对项不一致的分类计数（一条建议可属多类），按数量倒序
    anomalies: list[AnomalyCount] = Field(default_factory=list)


class UnboundNotify(StrictModel):
    """待通知供应商节点中、供应商未绑定企微开票群的任务汇总；没绑群就无法通知开票。"""

    suppliers: int
    tasks: int
    # 任务最多的前 5 家供应商名称
    names: list[str] = Field(default_factory=list)


class Workbench(StrictModel):
    generatedAt: str
    accounts: list[str]
    counts: WorkbenchCounts
    filteredCounts: WorkbenchCounts
    # 审核通过但没有开票任务（供应商均关闭通知）的报关单，不进漏斗与待办
    noTaskCount: int = 0
    # 供应商筛选选项（有效报关单关联的供应商）；suppliers 为待收票排名
    supplierOptions: list[SupplierOption] = Field(default_factory=list)
    items: list[Todo]
    total: int
    page: int
    pageSize: int
    pages: int
    kpis: list[Kpi] = Field(default_factory=list)
    suppliers: list[SupplierRank]
    unknownSupplierAmounts: int
    # 应开为全部报关关联子采购含税总额（含待审核，按月去重）；缺失创建时间的子单另计数。
    funnel: Funnel | None = None
    nodes: NodeDistribution | None = None
    monthly: list[MonthlyReceipt] = Field(default_factory=list)
    unknownExpectedDates: int = 0
    queue: QueueTiers | None = None
    unboundNotify: UnboundNotify | None = None


class WorkbenchExport(StrictModel):
    filename: str
    content: str
    count: int
