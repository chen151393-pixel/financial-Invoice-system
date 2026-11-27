"""应收看板响应；金额为两位小数字符串，应开缺失的任务只计件数（unknown）。"""

from backend.core.dto import StrictModel


class RecoverySummary(StrictModel):
    tasks: int
    suppliers: int
    amount: str
    unknown: int


class RecoveryCollected(RecoverySummary):
    rate: float | None = None


class RecoveryOutstanding(RecoverySummary):
    daysLeft: int | None = None


class RecoveryOverdue(RecoverySummary):
    longOverdue: int
    months: list[str]


class RecoveryCards(StrictModel):
    due: RecoverySummary
    collected: RecoveryCollected
    outstanding: RecoveryOutstanding
    overdue: RecoveryOverdue


class RecoveryMonth(StrictModel):
    month: str
    label: str
    dueDate: str
    state: str
    tasks: int
    collected: int
    rate: float | None = None
    expected: str
    collectedAmount: str
    outstandingAmount: str
    unknown: int


class RecoveryBuyer(StrictModel):
    memberId: str
    name: str
    tasks: int
    outstanding: int
    rate: float | None = None


class RecoveryShare(StrictModel):
    supplierId: int | None = None
    name: str
    amount: str
    share: float | None = None


class RecoveryConcentration(StrictModel):
    amount: str
    suppliers: int
    top: list[RecoveryShare]
    topAmount: str
    topShare: float | None = None
    restSuppliers: int
    restAmount: str
    restShare: float | None = None


class RecoveryTask(StrictModel):
    taskId: str
    recordNo: str
    orders: list[str]
    expected: str | None = None
    received: str | None = None
    outstanding: str | None = None
    approvedOn: str
    # 旧看板客户端的日期字段别名；一版本后移除，不表示供应商实际通知时间。
    notifiedOn: str
    dueDate: str
    collected: bool
    node: str
    nodeLabel: str


class RecoveryGroup(StrictModel):
    key: str
    supplierId: int | None = None
    supplierName: str
    companyId: int | None = None
    companyName: str
    memberId: str
    memberName: str
    tasks: int
    amount: str
    unknown: int
    approvedOn: str
    notifiedOn: str
    dueDate: str
    daysLeft: int | None = None
    items: list[RecoveryTask]


class RecoveryList(StrictModel):
    view: str
    summary: RecoverySummary
    items: list[RecoveryGroup]
    total: int
    page: int
    pageSize: int
    pages: int


class RecoveryOption(StrictModel):
    id: str
    name: str


class RecoveryOptions(StrictModel):
    buyers: list[RecoveryOption]
    companies: list[RecoveryOption]
    months: list[RecoveryOption]


class RecoveryBoard(StrictModel):
    today: str
    month: str
    monthLabel: str
    dueDate: str | None = None
    defaultMonth: str
    cards: RecoveryCards
    months: list[RecoveryMonth]
    recentRate: float | None = None
    buyers: list[RecoveryBuyer]
    concentration: RecoveryConcentration
    list: RecoveryList
    options: RecoveryOptions


class RecoveryExport(StrictModel):
    filename: str
    content: str
    count: int
