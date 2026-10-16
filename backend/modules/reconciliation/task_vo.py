"""开票跟进展示契约；未接入的收票数量为null，不能冒充零张。"""

from typing import Literal

from backend.core.dto import StrictModel


class TaskCapability(StrictModel):
    allowed: bool = False
    reason: str


class TaskSummary(StrictModel):
    id: str
    account: str
    recordNumber: str
    supplier: str
    company: str
    currency: str
    status: Literal["documents_pending", "notify_pending", "awaiting_invoice", "superseded"]
    statusLabel: str
    reason: str
    createdAt: str
    reviewRevision: int
    snapshotId: str
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
    quantity: str
    unit: str
    amount: str
    currency: str


class TaskDetail(StrictModel):
    task: TaskSummary
    lines: list[TaskLine]
    reasons: list[str]
    sourceStatus: Literal["current", "changed", "unavailable", "superseded"]
    sourceMessage: str
    prepare: TaskCapability
    notify: TaskCapability
    compare: TaskCapability
    steps: list["TaskStep"]
    documents: list["TaskDocument"]
    downloadEnvironment: str
    notification: "NotificationDetail"


class TaskDocument(StrictModel):
    orderId: str
    orderNumber: str
    status: Literal["pending", "archive_pending", "ready"]
    environment: str
    nsId: str = ""
    filename: str = ""
    sha256: str = ""
    downloadedAt: str | None = None
    archivePath: str | None = None
    archivedAt: str | None = None
    prepare: TaskCapability


class TaskStep(StrictModel):
    label: str
    description: str
    state: Literal["done", "current", "waiting"]


class NotificationEvent(StrictModel):
    revision: int
    actor: str
    at: str
    groupName: str
    employee: str
    message: str
    sentAt: str | None = None
    note: str = ""
    attachments: list[str] = []


class NotificationGroup(StrictModel):
    groupName: str
    chatId: str
    employee: str
    userid: str
    revision: int


class NotificationDetail(StrictModel):
    supplierGroup: NotificationGroup | None = None
    groupConfigReason: str = ""
    revision: int
    groupName: str
    employee: str
    message: str
    defaultMessage: str
    statusLabel: str
    edit: TaskCapability
    record: TaskCapability
    send: TaskCapability
    history: list[NotificationEvent]
