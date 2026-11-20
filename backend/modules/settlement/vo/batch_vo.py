"""结汇响应：路径、状态文案、金额核对与可操作判断均由服务器给出；金额为十进制字符串。"""

from typing import Literal

from backend.core.dto import StrictModel

Route = Literal["hk_transit", "direct"]
Status = Literal["collected", "documents_ready", "settled", "cancelled"]
# 处理方式：香港中转登记回款建批次；直接收汇进直接收汇明细（总账）
Handling = Literal["batch", "ledger"]


class Action(StrictModel):
    allowed: bool
    reason: str


class BatchActions(StrictModel):
    documentsReady: Action
    settle: Action
    cancel: Action


class Candidate(StrictModel):
    declarationNo: str
    recordNo: str
    consignee: str
    # 出口抬头：NS 报关单的申报主体；未知时为空串
    exportCompany: str
    exportDate: str
    salesOrders: list[str]
    currency: str
    amount: str
    route: Route
    routeLabel: str
    routeBasis: str
    handling: Handling
    handlingLabel: str
    # 报关单本身的问题或占用（已在其他批次、金额缺失等）；handling 为 batch 且此项为空才可选入批次
    blockedReason: str
    batchNo: str


class RouteTotal(StrictModel):
    route: Route
    routeLabel: str
    count: int
    currency: str
    amount: str


class CurrencyTotal(StrictModel):
    count: int
    currency: str
    amount: str


class ConsigneeTotal(StrictModel):
    """一家境外收货人（按币种分开）的应收汇汇总。"""

    consignee: str
    currency: str
    route: Route
    routeLabel: str
    routeBasis: str
    handling: Handling
    handlingLabel: str
    exportCompanies: list[str]
    count: int
    firstExportDate: str
    lastExportDate: str
    # 金额有效的报关单成交总价合计
    amount: str
    # 香港中转：已在有效批次中的张数、可登记回款建批次的张数
    batchedCount: int
    pendingCount: int
    # 金额或币制有问题、未计入合计的张数
    issueCount: int


class CandidateList(StrictModel):
    # 最多列出 500 张；total 为符合筛选的全部张数，超出时 truncated 为真
    items: list[Candidate]
    total: int
    truncated: bool
    # 以下汇总按符合筛选的全部报关单计算，不受列出张数限制
    totals: list[RouteTotal]
    # 香港中转与直接收汇按币种合计，不受明细列出张数限制。
    combinedTotals: list[CurrencyTotal]
    # 未在批次中、金额有效的报关单按路径汇总
    unsettled: list[RouteTotal]
    consignees: list[ConsigneeTotal]
    suggestion: list[str] | None
    suggestionNote: str


class Balance(StrictModel):
    stage: Literal["received", "remitted"]
    label: str
    arrived: str
    fee: str
    difference: str
    balanced: bool
    warnings: list[str]


class BatchItem(StrictModel):
    declarationNo: str
    recordNo: str
    salesOrders: str
    consignee: str
    exportDate: str
    currency: str
    amount: str


class BatchSummary(StrictModel):
    id: int
    batchNo: str
    route: Route
    routeLabel: str
    status: Status
    statusLabel: str
    consignee: str
    currency: str
    declaredTotal: str
    receivedOn: str
    receivedAmount: str
    receivedFee: str
    remittedOn: str
    remittedAmount: str
    remittedFee: str
    declarationCount: int
    balances: list[Balance]
    actions: BatchActions


class BatchDetail(BatchSummary):
    receivedSlipName: str = ""
    receivedSlipUrl: str = ""
    payer: str
    receivingAccount: str
    receivedReference: str
    remittedReference: str
    note: str
    createdBy: str
    createdAt: str
    documentsReadyBy: str
    documentsReadyAt: str
    settledBy: str
    settledAt: str
    cancelledBy: str
    cancelReason: str
    items: list[BatchItem]


class StatusCount(StrictModel):
    route: Route
    status: Status
    label: str
    count: int


class BatchList(StrictModel):
    items: list[BatchSummary]
    total: int
    page: int
    pageSize: int
    counts: list[StatusCount]
