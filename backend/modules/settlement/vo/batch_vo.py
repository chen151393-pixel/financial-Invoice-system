"""结汇响应：路径、状态文案、金额核对与可操作判断均由服务器给出；金额为十进制字符串。"""

from typing import Literal

from backend.core.dto import StrictModel

Route = Literal["hk_transit", "direct"]
Status = Literal["collected", "documents_ready", "settled", "cancelled"]


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
    exportDate: str
    salesOrders: list[str]
    currency: str
    amount: str
    route: Route
    routeLabel: str
    routeBasis: str
    # 不能选入批次的原因（已在其他批次、金额缺失等）；为空表示可选
    blockedReason: str
    batchNo: str


class RouteTotal(StrictModel):
    route: Route
    routeLabel: str
    count: int
    currency: str
    amount: str


class CandidateList(StrictModel):
    items: list[Candidate]
    unsettled: list[RouteTotal]
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
