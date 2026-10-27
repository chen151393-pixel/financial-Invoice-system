"""财务核对响应：展示数据、审核状态与能否审核均由服务器返回；金额、数量为十进制字符串。"""

from typing import Literal

from pydantic import Field

from backend.core.dto import StrictModel


class UnitPriceMargin(StrictModel):
    """按单价计算的幅度；人民币单价保留换算精度，前端不重算。"""

    margin: str = ""
    marginStatus: Literal["ok", "negative", "unavailable"] = "unavailable"
    marginNote: str = ""
    declaredUnitPriceCny: str = ""
    combinedPurchaseUnitPrice: str = ""


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


class PurchaseGroup(PurchaseLine):
    members: list[PurchaseLine] = Field(default_factory=list)


class CustomsLine(UnitPriceMargin):
    id: str
    parent: str = ""
    originPlace: str = ""
    lineNo: int
    name: str
    model: str
    quantity: str
    unit: str
    price: str
    amount: str
    currency: str
    purchaseCount: int
    purchaseLines: list[PurchaseGroup]


class ReviewState(StrictModel):
    status: Literal["pending", "approved", "unshipped"]
    label: str
    allowed: bool
    reason: str
    revision: int | None = None
    reviewedAt: str | None = None
    reviewedBy: str | None = None
    note: str = ""


class CurrencyCheck(StrictModel):
    purchaseOrderId: str
    orderNumber: str
    currency: str
    allowed: bool
    reason: str


class AutoReview(StrictModel):
    eligible: bool = False
    # 不能自动审核的原因（eligible 为 False 时）
    reasons: list[str] = Field(default_factory=list)


class Declaration(StrictModel):
    salesOrders: str = ""
    # 任一报关行申报幅度为负数时为 True，列表主行突出显示
    marginAlert: bool = False
    autoReview: AutoReview = Field(default_factory=AutoReview)
    currencyEvidenceSummary: list[str] = Field(default_factory=list)
    currencyChecks: list[CurrencyCheck] = Field(default_factory=list)
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
    unlinkedLines: list[PurchaseGroup]
    warnings: list[str]
    review: ReviewState


class SupplierOption(StrictModel):
    id: str
    name: str


class ReviewList(StrictModel):
    groups: list[Declaration]
    counts: dict[str, int]
    notices: list[str] = Field(default_factory=list)
    accounts: list[str] = Field(default_factory=list)
    suppliers: list[SupplierOption] = Field(default_factory=list)
    page: int = 1
    pageSize: int = 20
    total: int = 0
    pages: int = 1


class BatchItemResult(StrictModel):
    id: str
    recordNumber: str = ""
    reason: str = ""


class BatchApproveResult(StrictModel):
    """逐张结果：approved 已审核通过；skipped 未通过及原因（如来源已变化、未出库）。"""

    approved: list[BatchItemResult]
    skipped: list[BatchItemResult]
