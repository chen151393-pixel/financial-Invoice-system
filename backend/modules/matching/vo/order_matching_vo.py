"""整单候选：金额数量均由后端汇总，保留每一条实际分配预览。"""

from backend.core.dto import StrictModel

from .matching_vo import Capability


class OrderAllocationPreview(StrictModel):
    invoiceItemId: str
    purchaseLineId: str
    purchaseBasisId: str
    item: str
    invoiceUnit: str
    purchaseUnit: str
    invoiceQuantity: str
    purchaseQuantity: str
    amount: str


class OrderCandidate(StrictModel):
    purchaseOrderId: str
    orderNo: str
    parentOrderNo: str
    account: str
    supplier: str
    company: str
    currency: str
    lineCount: int
    remainingAmount: str | None
    remainingQuantity: str | None
    unit: str
    orderMatched: bool
    fingerprint: str
    warnings: list[str]
    confirm: Capability
    allocations: list[OrderAllocationPreview]


class OrderCandidates(StrictModel):
    rows: list[OrderCandidate]
    total: int
    page: int
    pages: int
