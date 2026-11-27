"""开票跟进响应：金额、数量为十进制字符串。"""

from typing import Literal

from pydantic import Field

from backend.core.dto import StrictModel

from .capability import Capability
from .notification_vo import NotificationBatchTarget, NotificationDetail
from .task_history_vo import TaskHistoryRecord

TaskStatus = Literal[
    "documents_pending",
    "notify_pending",
    "awaiting_invoice",
    "partially_received",
    "documents_incomplete",
    "completed",
    "superseded",
]


class TaskSummary(StrictModel):
    id: str
    account: str
    recordNumber: str
    declarationNumber: str = ""
    supplier: str
    company: str
    currency: str
    status: TaskStatus
    statusLabel: str
    # 本任务所处业务状态（待通知开票、待核票、资料已回、开票完成）；已被替代的任务为空
    stage: str = ""
    stageLabel: str = ""
    reason: str
    createdAt: str
    predecessorTaskIds: list[str]
    reviewRevision: int
    orderNumbers: list[str]
    lineCount: int
    expectedAmount: str | None = None
    receivedAmount: str | None = None
    outstandingAmount: str | None
    receiptPercent: str | None
    receiptBarPercent: str | None
    followupEmployee: str
    lastContactAt: str | None
    waitingLabel: str


class TaskCounts(StrictModel):
    tasks: int
    awaitingInvoice: int
    completed: int
    needsAttention: int


class TaskGroup(StrictModel):
    id: str
    label: str
    account: str
    counts: TaskCounts
    tasks: list[TaskSummary]


class SupplierOption(StrictModel):
    id: str
    name: str


class TaskList(StrictModel):
    groupBy: Literal["supplier", "declaration"]
    groups: list[TaskGroup]
    counts: TaskCounts
    accounts: list[str]
    suppliers: list[SupplierOption] = Field(default_factory=list)
    total: int
    page: int
    pageSize: int
    pages: int


class TaskLine(StrictModel):
    taskId: str = ""
    purchaseBasisId: str | None
    ledgerSha256: str | None
    requiresReview: bool
    pendingQuantity: str
    pendingAmount: str
    close: Capability
    id: str
    order: str
    name: str
    specification: str
    quantity: str
    unit: str
    amount: str
    currency: str
    receivedQuantity: str
    receivedAmount: str
    status: Literal["open", "partial", "received", "superseded"]
    statusLabel: str


class TaskDocument(StrictModel):
    taskId: str = ""
    recordNumber: str = ""
    declarationNumber: str = ""
    orderId: str
    orderNumber: str
    status: Literal["pending", "failed", "ready"]
    environment: str
    nsId: str = ""
    filename: str = ""
    sha256: str = ""
    downloadedAt: str | None = None
    archivePath: str | None = None
    archivedAt: str | None = None
    error: str = ""
    prepare: Capability


class ArchivedFile(StrictModel):
    filename: str
    path: str


class DeclarationDocument(StrictModel):
    """报关资料（报关单、销售合同、发票）：按报关单各一份，各供应商任务共用。"""

    taskId: str = ""
    recordNumber: str = ""
    type: Literal["customs_declaration", "sales_contract", "invoice"]
    label: str
    status: Literal["unregistered", "pending", "archived", "failed"]
    statusLabel: str
    files: list[ArchivedFile]
    error: str = ""
    attempts: int = 0
    archivedAt: str | None = None
    retry: Capability


class SignedContract(StrictModel):
    orderId: str
    orderNumber: str
    uploaded: bool
    filename: str = ""
    archivePath: str | None = None
    uploadedAt: str | None = None
    uploadedBy: str = ""


class TaskReviewRow(StrictModel):
    taskId: str
    recordNumber: str
    declarationNumber: str
    reviewRevision: int
    customsStatusLabel: str
    financeStatusLabel: str
    orderCount: int


class TaskDeclarationRow(StrictModel):
    taskId: str
    recordNumber: str
    declarationNumber: str
    customs: DeclarationDocument | None = None
    sales: DeclarationDocument | None = None
    invoice: DeclarationDocument | None = None


class TaskPreparation(StrictModel):
    contractCount: int
    archivedCount: int
    contractsReady: bool
    contractSummary: str
    declarationCount: int
    signedPendingCount: int
    signedSummary: str
    note: str


class TaskCompletion(StrictModel):
    """资料齐全情况：子采购合同、报关单、销售合同、发票、回签合同全部到齐才算齐全。"""

    ready: bool
    missing: list[str]
    reason: str


class TaskStep(StrictModel):
    # review / documents / notification / invoices / comparison / completion
    key: str
    label: str
    description: str
    # skipped：后续事实已发生而本节点事实未发生（如未通知即收票），流程不停留在此
    state: Literal["done", "current", "waiting", "skipped"]


class TaskEvent(StrictModel):
    at: str
    actor: str
    label: str
    reason: str


class TaskDetail(StrictModel):
    grouped: bool = False
    memberTasks: list[TaskSummary] = Field(default_factory=list)
    reviewRows: list[TaskReviewRow] = Field(default_factory=list)
    declarationRows: list[TaskDeclarationRow] = Field(default_factory=list)
    preparation: TaskPreparation | None = None
    scopeRevision: str = ""
    notificationTaskId: str = ""
    task: TaskSummary
    lines: list[TaskLine]
    reasons: list[str]
    sourceStatus: Literal["current", "superseded"]
    sourceMessage: str
    prepare: Capability
    notify: Capability
    compare: Capability
    steps: list[TaskStep]
    documents: list[TaskDocument]
    # 本次通知范围内的全部合同，保留各原任务的归档状态；单任务沿用 documents。
    notificationDocuments: list[TaskDocument] | None = None
    declarationDocuments: list[DeclarationDocument] = Field(default_factory=list)
    signedContracts: list[SignedContract] = Field(default_factory=list)
    completion: TaskCompletion | None = None
    downloadEnvironment: str
    notification: NotificationDetail
    events: list[TaskEvent]
    history: list[TaskHistoryRecord] = Field(default_factory=list)


class BoardNode(StrictModel):
    """采购任务台分区：当前节点为该节点的任务数（全部筛选结果，不只本页）。"""

    key: Literal["documents", "notification", "invoices", "comparison", "completion", "done"]
    label: str
    hint: str
    count: int


class BoardItem(StrictModel):
    grouped: bool = False
    taskIds: list[str] = Field(default_factory=list)
    task: TaskSummary
    steps: list[TaskStep]
    currentNode: str
    currentLabel: str
    nextAction: str
    # 来源或开票依据变化时不能继续推进，需财务重新审核
    blockedReason: str = ""
    missing: list[str]
    # 能否在列表勾选后批量登记“线下已通知”；提交时后端逐个任务重新校验
    notifyRecord: Capability
    # 本次允许批量登记的原任务；已通知及当前不可登记成员不在此范围。
    notifyTargets: list[NotificationBatchTarget] = Field(default_factory=list)
    notifyScopeRevision: str = ""


class TaskBoard(StrictModel):
    nodes: list[BoardNode]
    # 进行中（未完成、未被替代）的任务总数
    openTotal: int
    items: list[BoardItem]
    suppliers: list[SupplierOption]
    total: int
    page: int
    pageSize: int
    pages: int
