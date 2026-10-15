"""发票比对响应：金额、数量、置信度为十进制字符串；可执行操作返回 allowed/reason。"""

from typing import Literal

from backend.core.dto import StrictModel

Tier = Literal["high", "medium", "low", "manual"]


class Capability(StrictModel):
    allowed: bool = False
    reason: str


class Check(StrictModel):
    key: str
    label: str
    invoiceValue: str | None
    purchaseValue: str | None
    result: Literal["match", "partial", "mismatch", "missing"]
    difference: str | None
    note: str


class PurchaseSide(StrictModel):
    purchaseLineId: str
    orderNo: str
    supplier: str
    company: str
    item: str
    specification: str
    unit: str
    currency: str
    currencyNote: str
    expectedQuantity: str | None
    expectedAmount: str | None
    receivedQuantity: str | None
    receivedAmount: str | None
    remainingQuantity: str | None
    remainingAmount: str | None
    recordNumber: str
    taskId: str | None


class AllocationView(StrictModel):
    id: str
    invoiceItemId: str
    purchaseLineId: str
    quantity: str
    amount: str
    status: Literal["proposed", "confirmed", "rejected", "cancelled"]
    statusLabel: str
    confidence: str | None
    tier: Tier
    checks: list[Check]
    exceedsExpected: bool
    closesPurchaseLine: bool
    proposedBy: str
    proposedAt: str
    reviewedBy: str | None
    reviewedAt: str | None
    reviewNote: str | None
    cancelledBy: str | None
    cancelledAt: str | None
    cancelReason: str | None
    purchase: PurchaseSide | None
    confirm: Capability
    noteReasons: list[str]
    reject: Capability
    cancel: Capability


class ItemView(StrictModel):
    id: str
    lineNo: str | None
    item: str | None
    specification: str | None
    unit: str | None
    quantity: str | None
    amount: str | None
    confirmedQuantity: str
    confirmedAmount: str
    allocations: list[AllocationView]


class InvoiceSide(StrictModel):
    id: str
    number: str
    date: str | None
    seller: str | None
    buyer: str | None
    status: str
    statusLabel: str
    currency: str
    gross: str | None
    remark: str | None


class InvoiceMatching(StrictModel):
    invoice: InvoiceSide
    items: list[ItemView]
    generate: Capability


class QueueRow(StrictModel):
    allocation: AllocationView
    invoiceId: str
    invoiceNumber: str
    seller: str | None
    itemName: str | None


class Queue(StrictModel):
    rows: list[QueueRow]
    total: int
    page: int
    pageSize: int
    pages: int
    counts: dict[str, int]


class SummaryRow(StrictModel):
    invoiceId: str
    status: Literal["none", "proposed", "partial", "confirmed"]
    label: str
    tier: Tier | None
    proposed: int
    confirmed: int


class Summaries(StrictModel):
    rows: list[SummaryRow]


class Candidate(StrictModel):
    purchase: PurchaseSide
    checks: list[Check]
    confidence: str
    tier: Tier
    block: str


class Candidates(StrictModel):
    rows: list[Candidate]
    total: int


class Skipped(StrictModel):
    id: str
    reason: str


class BatchResult(StrictModel):
    confirmed: int
    skipped: list[Skipped]


class GenerateResult(StrictModel):
    created: int
