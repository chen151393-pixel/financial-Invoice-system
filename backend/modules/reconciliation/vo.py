"""前端展示的数据、审核能力和禁用原因均由服务器返回。"""

from typing import Literal

from pydantic import Field

from backend.core.dto import StrictModel


class PurchaseLine(StrictModel):
    id: str
    name: str
    model: str
    parent: str
    child: str
    supplier: str
    quantity: str
    unit: str
    price: str
    amount: str
    currency: str
    note: str
    scope: Literal["declared", "order"] = "declared"


class CustomsLine(StrictModel):
    id: str
    lineNo: int
    name: str
    model: str
    quantity: str
    unit: str
    price: str
    amount: str
    currency: str
    purchaseCount: int
    purchaseLines: list[PurchaseLine]


class ReviewState(StrictModel):
    status: Literal["pending", "approved", "blocked"]
    label: str
    allowed: bool
    reason: str
    reviewedAt: str | None = None
    reviewedBy: str | None = None
    note: str = ""


class Declaration(StrictModel):
    id: str
    invoiceTaskCount: int | None = None
    snapshotId: str = ""
    account: str = ""
    recordNumber: str
    declaration: str
    pl: str
    company: str
    customsCount: int
    purchaseCount: int
    customsLines: list[CustomsLine]
    unlinkedLines: list[PurchaseLine]
    warnings: list[str]
    review: ReviewState


class ReviewResult(StrictModel):
    source: Literal["netsuite", "database"] = "netsuite"
    requestId: str
    readCompletedAt: str
    groups: list[Declaration]
    counts: dict[str, int]
    notices: list[str] = Field(default_factory=list)
    accounts: list[str] = Field(default_factory=list)
    page: int = 1
    pageSize: int = 20
    total: int = 0
    pages: int = 1
