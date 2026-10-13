"""开票跟进响应：金额、数量为十进制字符串；未接入的收票统计为 null，不冒充零。"""

from typing import Literal

from backend.core.dto import StrictModel

from .capability import Capability
from .notification_vo import NotificationDetail

TaskStatus = Literal[
    "documents_pending", "notify_pending", "awaiting_invoice", "partially_received", "completed", "superseded"
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
    reason: str
    createdAt: str
    reviewRevision: int
    orderNumbers: list[str]
    lineCount: int
    expectedAmount: str | None = None


class TaskCounts(StrictModel):
    tasks: int
    awaitingInvoice: int
    receivedInvoices: int | None = None
    needsAttention: int


class TaskGroup(StrictModel):
    id: str
    label: str
    account: str
    counts: TaskCounts
    tasks: list[TaskSummary]


class TaskList(StrictModel):
    groupBy: Literal["supplier", "declaration"]
    groups: list[TaskGroup]
    counts: TaskCounts
    accounts: list[str]
    total: int
    page: int
    pageSize: int
    pages: int


class TaskLine(StrictModel):
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
    downloadEnvironment: str
    notification: NotificationDetail
    events: list[TaskEvent]
