"""发票比对响应：金额、数量、置信度为十进制字符串；可执行操作返回 allowed/reason。"""

from typing import Literal

from pydantic import Field

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
    # 展示文字由后端推导：分次收票、发票多/少等，前端直接显示
    resultLabel: str
    differenceLabel: str | None


class PurchaseSide(StrictModel):
    purchaseBasisId: str | None = None
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
    invoiceVersionId: str | None
    currentInvoiceVersionId: str | None
    purchaseBasisId: str | None
    purchaseQuantity: str | None
    verificationStatus: str
    verificationIssues: list[str]
    reverify: Capability
    replace: Capability
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
    active: bool
    id: str
    lineNo: str | None
    item: str | None
    specification: str | None
    unit: str | None
    quantity: str | None
    amount: str | None
    # 票面展示：单价、不含税金额、税率（如“13%”）、税额，均为后端文本；金额两位小数带千分位
    unitPrice: str | None = None
    net: str | None = None
    taxRate: str | None = None
    tax: str | None = None
    confirmedQuantity: str
    confirmedAmount: str
    allocations: list[AllocationView]


class InvoiceSide(StrictModel):
    versionId: str | None
    detailStatus: str
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


class GroupOrder(StrictModel):
    purchaseOrderId: str
    orderNo: str
    parentOrderNo: str
    supplier: str
    company: str
    lineCount: int


class GroupLine(StrictModel):
    """整单所含子采购明细（只读展开）。"""

    purchaseLineId: str
    orderNo: str
    item: str
    specification: str
    unit: str
    quantity: str
    amount: str
    taxRate: str | None


class GroupItem(StrictModel):
    """一条发票行与所选整单合计的比对。"""

    invoiceItemId: str
    checks: list[Check]
    confidence: str | None
    tier: str
    quantity: str
    amount: str
    lines: list[GroupLine]


class GroupView(StrictModel):
    """整单建议：整组通过或驳回；allocationIds 为组内逐条记账的分配记录。"""

    id: str
    orders: list[GroupOrder]
    items: list[GroupItem]
    confidence: str | None
    tier: str
    noteReasons: list[str]
    confirm: Capability
    reject: Capability
    allocationIds: list[str]


class InvoicePaper(StrictModel):
    """比对详情页票面补充信息；只读展示，不参与比对。"""

    invoiceType: str | None
    buyerTaxNo: str | None
    sellerTaxNo: str | None
    net: str | None
    tax: str | None
    gross: str | None


class InvoiceMatching(StrictModel):
    invoice: InvoiceSide
    paper: InvoicePaper
    # 待审核的整单建议；组内分配同时出现在各发票行 allocations 中
    groups: list[GroupView] = Field(default_factory=list)
    # 已关联且依据有效的完整整单，保留审核时比对，不能重复审核。
    linkedGroups: list[GroupView] = Field(default_factory=list)
    items: list[ItemView]
    generate: Capability


class QueueRow(StrictModel):
    allocation: AllocationView
    invoiceId: str
    invoiceNumber: str
    seller: str | None
    itemName: str | None
    # 异常分类（价格、数量、单位等）；空表示正常
    anomalies: list[str] = Field(default_factory=list)


class SupplierOption(StrictModel):
    id: str
    name: str


class Queue(StrictModel):
    rows: list[QueueRow]
    total: int
    page: int
    pageSize: int
    pages: int
    counts: dict[str, int]
    suppliers: list[SupplierOption] = Field(default_factory=list)
    # 按异常筛选时最多核对的建议条数；超过时只在前若干条中筛选，并给出提示
    notice: str = ""


class SummaryRow(StrictModel):
    invoiceId: str
    status: Literal["none", "proposed", "partial", "confirmed", "needs_review", "excluded"]
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
