"""结汇请求：金额为十进制字符串（最多两位小数）；操作者来自认证身份，不接受前端提交。"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from backend.core.dto import StrictModel

Text200 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Text500 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Number = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


def amount_value(value, label, *, allow_zero):
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label}不是有效数值") from None
    if (
        not number.is_finite()
        or number < 0
        or (number == 0 and not allow_zero)
        or number >= Decimal(10) ** 16
    ):
        raise ValueError(f"{label}须为范围内的{'非负数' if allow_zero else '正数'}")
    if number != number.quantize(Decimal("0.01")):
        raise ValueError(f"{label}最多两位小数")
    return number


class CandidateQuery(StrictModel):
    consignee: Text200 = ""
    declarationNo: Text200 = ""
    route: Literal["all", "hk_transit", "direct"] = "all"
    exportFrom: date | None = Field(default=None, strict=False)
    exportTo: date | None = Field(default=None, strict=False)
    # 填写后按“到账 + 手续费”推荐金额恰好吻合的香港中转报关单组合
    targetAmount: str = ""

    @field_validator("targetAmount", mode="before")
    @classmethod
    def valid_target(cls, value):
        if value in (None, ""):
            return ""
        return str(amount_value(value, "目标金额", allow_zero=False))

    @model_validator(mode="after")
    def valid_export_dates(self):
        if self.exportFrom and self.exportTo and self.exportFrom > self.exportTo:
            raise ValueError("出口日期开始不能晚于结束")
        return self


class CreateBatchRequest(StrictModel):
    requestId: UUID = Field(strict=False)
    declarationNos: list[Number] = Field(min_length=1, max_length=200)
    receivedOn: date = Field(strict=False)
    receivedAmount: Decimal
    receivedFee: Decimal = Decimal(0)
    payer: Text500 = ""
    receivingAccount: Text200 = ""
    receivedReference: Text200 = ""
    note: Text500 = ""

    @field_validator("receivedAmount", mode="before")
    @classmethod
    def valid_amount(cls, value):
        return amount_value(value, "到账金额", allow_zero=False)

    @field_validator("receivedFee", mode="before")
    @classmethod
    def valid_fee(cls, value):
        return amount_value(value, "手续费", allow_zero=True)

    @model_validator(mode="after")
    def unique_numbers(self):
        if len(set(self.declarationNos)) != len(self.declarationNos):
            raise ValueError("报关单号不能重复")
        return self


class RemittanceRequest(StrictModel):
    """香港中转：登记香港汇回境内的到账并确认结汇。"""

    remittedOn: date = Field(strict=False)
    remittedAmount: Decimal
    remittedFee: Decimal = Decimal(0)
    remittedReference: Text200 = ""

    @field_validator("remittedAmount", mode="before")
    @classmethod
    def valid_amount(cls, value):
        return amount_value(value, "汇回金额", allow_zero=False)

    @field_validator("remittedFee", mode="before")
    @classmethod
    def valid_fee(cls, value):
        return amount_value(value, "汇回手续费", allow_zero=True)


class CancelRequest(StrictModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class BatchQuery(StrictModel):
    route: Literal["all", "hk_transit", "direct"] = "all"
    status: Literal["all", "open", "collected", "documents_ready", "settled", "cancelled"] = "open"
    consignee: Text200 = ""
    batchNo: Text200 = ""
    declarationNo: Text200 = ""
    receivedFrom: date | None = Field(default=None, strict=False)
    receivedTo: date | None = Field(default=None, strict=False)
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.receivedFrom and self.receivedTo and self.receivedFrom > self.receivedTo:
            raise ValueError("到账日期开始不能晚于结束")
        return self
