"""财务核对响应：展示数据、审核状态与能否审核均由服务器返回；金额、数量为十进制字符串。"""

from typing import Literal

from pydantic import AliasChoices, Field

from backend.core.dto import StrictModel


class UnitPriceMargin(StrictModel):
    """按单价计算的幅度；人民币单价保留换算精度，前端不重算。"""

    margin: str = ""
    # unit_mismatch / quantity_mismatch：报关行原始口径与报关口径单位或数量不一致，不计算幅度
    marginStatus: Literal["ok", "negative", "unavailable", "unit_mismatch", "quantity_mismatch"] = (
        "unavailable"
    )
    marginNote: str = ""
    declaredUnitPriceCny: str = ""
    # 报关行含税采购单价 ÷ 1.13 后折人民币；兼容旧键仅用于读取旧快照并显示“后台计算中”。
    originalUnitPriceCny: str = Field(
        default="", validation_alias=AliasChoices("originalUnitPriceCny", "combinedPurchaseUnitPrice")
    )
    originalPriceUnit: str = ""
    declaredPriceUnit: str = ""


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
    purchaseQuantity: str = ""
    purchaseUnit: str = ""
    amount: str
    currency: str
    salesOrderExchangeRate: str = ""
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
    # NS 未填申报单价时 price 为报关金额 ÷ 报关数量的试算值，页面标注“试算”
    priceEstimated: bool = False
    # 报关行原始口径（NS 数量、单价，单位见 originalPriceUnit），页面列名“采购单价”；旧快照缺省为空
    originalQuantity: str = ""
    originalPrice: str = ""
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
    purchaseOrderNumbers: list[str] = Field(default_factory=list)
    calculationStatus: Literal["ready", "pending", "failed"] = "ready"
    calculatedAt: str | None = None
    salesOrders: str = ""
    # 任一报关行采购单价超出人民币报关单价容差时为 True
    marginAlert: bool = False
    unitMismatch: bool = False
    quantityMismatch: bool = False
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
