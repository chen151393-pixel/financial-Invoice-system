"""Excel 导入预览与确认结果。"""

from typing import Literal

from backend.core.dto import StrictModel


class ImportConfiguration(StrictModel):
    allowed: bool
    reason: str
    maxBytes: int


class ImportRow(StrictModel):
    number: str
    date: str
    seller: str
    businessType: str
    status: str
    amount: str
    lineCount: int
    action: Literal["new", "updated", "unchanged", "conflict"]


class ImportResult(StrictModel):
    filename: str
    invoiceCount: int
    sourceInvoiceCount: int
    excludedCount: int
    businessType: str
    lineCount: int
    updated: int = 0
    created: int
    unchanged: int
    conflicts: int
    amount: str
    saved: bool
    allowed: bool
    reason: str
    previewToken: str | None
    message: str
    warnings: list[str]
    rows: list[ImportRow]
