"""报关单结汇详情：只读流程、冲抵依据、资料范围与真实操作记录。"""

from typing import Literal

from backend.core.dto import StrictModel

from .batch_vo import BatchDetail
from .document_vo import Bill, Contract, PlannedContract
from .receivable_vo import ReceivableItem


class DetailStep(StrictModel):
    key: str
    label: str
    description: str
    state: Literal["done", "current", "waiting"]
    percent: int


class ReceiptApplication(StrictModel):
    receiptId: int
    date: str
    reference: str
    receiptAmount: str
    appliedAmount: str
    payer: str
    thirdParty: bool


class AllocationRow(StrictModel):
    declarationNo: str
    exportDate: str
    amount: str
    receivedAmount: str
    outstandingAmount: str
    current: bool
    receipts: list[ReceiptApplication]


class DetailOriginal(StrictModel):
    statusLabel: str
    archived: bool
    files: list[dict[str, str]]
    note: str


class DetailContract(StrictModel):
    planned: PlannedContract | None
    contract: Contract | None
    label: str


class DetailDocuments(StrictModel):
    groupId: int | None = None
    scopeKind: Literal["batch", "single", "group", "none"]
    scopeLabel: str
    scopeNumbers: list[str]
    note: str
    original: DetailOriginal
    bills: list[Bill]
    contracts: list[DetailContract]
    issues: list[str]
    warnings: list[str]


class DetailEvent(StrictModel):
    at: str
    actor: str
    description: str


class DeclarationDetail(StrictModel):
    item: ReceivableItem
    steps: list[DetailStep]
    batch: BatchDetail | None
    allocations: list[AllocationRow]
    ledgerBalance: str
    ledgerNote: str
    documents: DetailDocuments
    events: list[DetailEvent]
    asOf: str
