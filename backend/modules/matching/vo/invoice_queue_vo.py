"""整票审核队列：计数、分页和批量可选记录均由后端给出。"""

from backend.core.dto import StrictModel

from .matching_vo import Capability, InvoiceSide, SupplierOption, Tier


class InvoiceQueueRow(StrictModel):
    invoice: InvoiceSide
    proposalCount: int
    purchaseOrders: list[str]
    confidence: str
    tier: Tier
    anomalies: list[str]
    batch: Capability
    batchIds: list[str]


class InvoiceQueue(StrictModel):
    rows: list[InvoiceQueueRow]
    total: int
    page: int
    pageSize: int
    pages: int
    counts: dict[str, int]
    suppliers: list[SupplierOption]
