"""版本 3 只读账单契约：按母单分组，金额为十进制字符串。"""

from typing import Annotated, Literal

from pydantic import Field, field_validator

from backend.core.dto import StrictModel

from ..dto.vendor_bill_query import NsId, VendorBillQuery

Money = Annotated[str, Field(pattern=r"^-?(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,2})?$")]
CentMoney = Annotated[str, Field(pattern=r"^-?(?:0|[1-9][0-9]{0,15})\.[0-9]{2}$")]


class VendorReference(StrictModel):
    id: NsId
    code: str = Field(max_length=100)
    name: str = Field(max_length=500)


class BillAmounts(StrictModel):
    remaining: CentMoney
    applied: CentMoney
    payable: CentMoney
    received: CentMoney
    available: CentMoney


class BillDetails(StrictModel):
    count: int = Field(ge=0, le=9007199254740991)
    total: CentMoney


class NsBill(StrictModel):
    billId: NsId
    billNumber: str = Field(min_length=1, max_length=200)
    vendorId: NsId
    purchaseOrderId: NsId
    subPurchaseOrderId: str = Field(pattern=r"^(?:[1-9][0-9]{0,19})?$")
    subsidiaryId: NsId
    currencyId: NsId
    currencyName: str = Field(max_length=100)
    approvalStatus: Literal["", "1", "2", "3"]
    voided: bool
    hasTax: bool
    amounts: BillAmounts
    details: BillDetails
    consistent: bool


class MissingPurchase(StrictModel):
    id: NsId
    status: Literal["PO_NOT_FOUND"]
    bills: list[NsBill] = Field(max_length=0)


class PurchaseBills(StrictModel):
    id: NsId
    number: str = Field(min_length=1, max_length=100)
    vendorId: NsId
    subsidiaryId: NsId
    currencyId: NsId
    currencyName: str = Field(max_length=100)
    status: Literal["FOUND", "NO_BILLS", "VENDOR_MISMATCH"]
    bills: list[NsBill] = Field(max_length=200)


class NsBillResult(StrictModel):
    contractVersion: Literal[3]
    complete: Literal[True]
    source: Literal["vendor-bill-query"]
    account: str = Field(min_length=1, max_length=100)
    query: VendorBillQuery
    readStartedAt: str
    readCompletedAt: str
    status: Literal["OK", "VENDOR_NOT_FOUND"]
    vendor: VendorReference | None
    purchaseOrders: list[Annotated[PurchaseBills | MissingPurchase, Field(discriminator="status")]] = Field(
        max_length=20
    )

    @field_validator("contractVersion", "complete", mode="before")
    @classmethod
    def exact_literals(cls, value, info):
        expected = int if info.field_name == "contractVersion" else bool
        if type(value) is not expected:
            raise ValueError("脚本版本或完整性标志类型错误")
        return value


class WritebackDisabled(StrictModel):
    allowed: Literal[False] = False
    reason: str = "当前仅查询候选账单，尚未确认发票分配、审核或启用回写"


class VendorBill(NsBill):
    currency: str = Field(pattern=r"^(?:[A-Z]{3})?$")
    totalInvoiceAmount: CentMoney
    receivedInvoiceAmount: CentMoney
    availableInvoiceAmount: CentMoney
    issues: list[str]


class PurchaseBillView(PurchaseBills):
    bills: list[VendorBill] = Field(max_length=200)
    reason: str


class MissingPurchaseView(MissingPurchase):
    reason: str


class VendorBillResult(NsBillResult):
    purchaseOrders: list[Annotated[PurchaseBillView | MissingPurchaseView, Field(discriminator="status")]] = (
        Field(max_length=20)
    )
    queryId: str
    reason: str
    warnings: list[str]
    writeback: WritebackDisabled = Field(default_factory=WritebackDisabled)
