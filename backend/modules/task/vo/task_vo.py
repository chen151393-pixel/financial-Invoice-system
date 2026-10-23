"""开票跟进响应：金额、数量为十进制字符串。"""

from typing import Literal

from pydantic import Field

from backend.core.dto import StrictModel

from .capability import Capability
from .notification_vo import NotificationDetail

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


class TaskCompletion(StrictModel):
    """资料齐全情况：子采购合同、报关单、销售合同、发票、回签合同全部到齐才算齐全。"""

    ready: bool
    missing: list[str]
    reason: str


class TaskStep(StrictModel):
    label: str
    description: str
    state: Literal["done", "current", "waiting"]


class TaskEvent(StrictModel):
    at: str
    actor: str
    label: str
    reason: str


class TaskDetail(StrictModel):
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
    declarationDocuments: list[DeclarationDocument] = Field(default_factory=list)
    signedContracts: list[SignedContract] = Field(default_factory=list)
    completion: TaskCompletion | None = None
    downloadEnvironment: str
    notification: NotificationDetail
    events: list[TaskEvent]
