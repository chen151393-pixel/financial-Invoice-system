"""报关应收汇响应：已收、未收、阶段与资料状态全部由后端计算；金额为十进制字符串。"""

from backend.core.dto import StrictModel

from .batch_vo import Handling, Route


class StageCount(StrictModel):
    stage: str
    label: str
    count: int


class ReceivableItem(StrictModel):
    declarationNo: str
    recordNo: str
    consignee: str
    exportCompany: str
    exportDate: str
    salesOrders: list[str]
    currency: str
    amount: str
    route: Route
    routeLabel: str
    routeBasis: str
    # 已收：香港中转为批次到账 + 手续费冲抵结果；直接收汇为先出口先冲抵的推算结果
    receivedAmount: str
    outstandingAmount: str
    receivedBasis: str
    # 进度条宽度 0–100 与实际百分比文本，由后端计算
    receivedPercent: int
    receivedPercentText: str
    stage: str
    stageLabel: str
    agingDays: int | None
    alert: str
    issue: str
    batchId: int | None
    batchNo: str
    documentStatus: str
    documentLabel: str
    documentNote: str


class ReceivableCustomer(StrictModel):
    consignee: str
    currency: str
    route: Route
    routeLabel: str
    routeBasis: str
    handling: Handling
    exportCompanies: list[str]
    count: int
    issueCount: int
    firstExportDate: str
    lastExportDate: str
    amount: str
    receivedAmount: str
    outstandingAmount: str
    # 直接收汇按收款抬头推算后剩余的超收；香港中转为 0
    overpaidAmount: str
    receivedPercent: int
    receivedPercentText: str
    stages: list[StageCount]
    oldestAgingDays: int | None
    batchedCount: int
    pendingCount: int
    alertCount: int
    documentIssueCount: int
    documentNote: str


class ReceivableTotal(StrictModel):
    # all 为两条路径合计
    route: str
    routeLabel: str
    currency: str
    count: int
    amount: str
    receivedAmount: str
    outstandingAmount: str
    overpaidAmount: str
    # 香港中转：待登记回款张数与金额；直接收汇为 0
    pendingCount: int
    pendingAmount: str


class ReceivableList(StrictModel):
    items: list[ReceivableItem]
    total: int
    truncated: bool
    stages: list[StageCount]
    customers: list[ReceivableCustomer]
    totals: list[ReceivableTotal]
    asOf: str
