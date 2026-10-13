"""财务核对响应：展示数据、审核状态与能否审核均由服务器返回；金额、数量为十进制字符串。"""

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
    scope: Literal["declared", "order"] = "order"


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
    revision: int | None = None
    reviewedAt: str | None = None
    reviewedBy: str | None = None
    note: str = ""


class Declaration(StrictModel):
    id: str
    contentSha256: str
    account: str
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


class ReviewList(StrictModel):
    groups: list[Declaration]
    counts: dict[str, int]
    notices: list[str] = Field(default_factory=list)
    accounts: list[str] = Field(default_factory=list)
    page: int = 1
    pageSize: int = 20
    total: int = 0
    pages: int = 1
