"""香港中转阶段、待登记报关单与批次卡片。金额为十进制字符串。"""

from typing import Literal

from backend.core.dto import StrictModel

from .batch_vo import Action, BatchDetail


class HkStage(StrictModel):
    key: str
    label: str
    value: str
    note: str
    tone: Literal["primary", "warning", "progress", "info", "success", "neutral"]


class HkPending(StrictModel):
    declarationNo: str
    recordNo: str
    consignee: str
    exportCompany: str
    currency: str
    amount: str
    exportDate: str
    waitingLabel: str
    select: Action


class HkDocumentFlag(StrictModel):
    label: str
    ready: bool
    description: str


class HkStep(StrictModel):
    key: str
    label: str
    description: str
    state: Literal["done", "current", "waiting", "skipped"]


class HkBatch(StrictModel):
    batch: BatchDetail
    waitingLabel: str
    overdue: bool
    issue: str
    notice: str
    documents: list[HkDocumentFlag]
    steps: list[HkStep]
    packageUrl: str
    package: Action
    primaryLabel: str
    primaryAction: Literal["documents", "remit", "package", "view"]


class HkWorkbench(StrictModel):
    stages: list[HkStage]
    pending: list[HkPending]
    pendingTotal: int
    pendingPage: int
    pendingPageCount: int
    batches: list[HkBatch]
    batchTotal: int
    page: int
    pageCount: int
    asOf: str


class HkReceiptCheck(StrictModel):
    currency: str
    declaredTotal: str
    arrivedTotal: str
    difference: str
    balanced: bool
    warnings: list[str]
    submit: Action


class HkExport(StrictModel):
    fileName: str
    content: str
