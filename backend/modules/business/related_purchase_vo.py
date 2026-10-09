"""NS 子采购及报关只读来源响应；金额保持十进制文本。"""

from typing import Literal

from backend.core.dto import StrictModel


class RelatedPurchaseMissing(StrictModel):
    found: Literal[False]
    queriedAt: str


class RelatedPurchaseLine(StrictModel):
    name: str
    quantity: str
    amount: str


class RelatedCustoms(StrictModel):
    recordNo: str
    declarationNo: str
    date: str


class RelatedPurchaseFound(StrictModel):
    found: Literal[True]
    queriedAt: str
    subPurchaseNo: str
    parentPurchase: str
    purchaseDate: str
    supplier: str
    pl: str
    purchaseAmount: str | None
    invoiceGross: str
    amountMatches: bool | None
    customs: RelatedCustoms | None
    lines: list[RelatedPurchaseLine]
