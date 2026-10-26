"""发票比对请求：ID 与金额数量为十进制字符串；操作者来自认证身份，不接受前端提交。"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from backend.core.dto import StrictModel

Id = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,18}$")]
Note = Annotated[str, StringConstraints(max_length=300)]


def positive(value, label, scale):
    try:
        number = Decimal(value)
        if not number.is_finite() or number <= 0 or number >= Decimal(10) ** 16:
            raise ValueError(f"{label}须为范围内的正数")
        if number != number.quantize(Decimal(1).scaleb(-scale)):
            raise ValueError(f"{label}最多 {scale} 位小数")
        return number
    except ArithmeticError:
        raise ValueError(f"{label}不是有效数值") from None


class ConversionBody(StrictModel):
    conversionNumerator: Decimal = Decimal(1)
    conversionDenominator: Decimal = Decimal(1)
    conversionEvidence: str = Field(default="", max_length=500)
    invoiceVersionId: Id | None = None
    purchaseBasisId: Id | None = None

    @field_validator("conversionNumerator", "conversionDenominator", mode="before")
    @classmethod
    def valid_factor(cls, value):
        return positive(str(value), "换算因子", 12)


class ConfirmBody(ConversionBody):
    note: Note = ""
    closesPurchaseLine: bool = False


class RejectBody(StrictModel):
    note: Note = ""


class CancelBody(StrictModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class ManualBody(ConversionBody):
    requestId: UUID = Field(strict=False)
    invoiceId: Id
    invoiceItemId: Id
    purchaseLineId: Id
    quantity: Decimal
    amount: Decimal
    note: Note = ""
    closesPurchaseLine: bool = False

    @field_validator("quantity", mode="before")
    @classmethod
    def valid_quantity(cls, value):
        return positive(str(value), "数量", 8)

    @field_validator("amount", mode="before")
    @classmethod
    def valid_amount(cls, value):
        return positive(str(value), "金额", 2)


class BatchBody(StrictModel):
    ids: list[Id] = Field(min_length=1, max_length=100)


class GenerateBody(StrictModel):
    invoiceIds: list[Id] = Field(min_length=1, max_length=100)


class SummaryBody(StrictModel):
    invoiceIds: list[Id] = Field(min_length=1, max_length=100)


class QueueQuery(StrictModel):
    tier: Literal["all", "high", "medium", "low"] = "all"
    # 只看异常 / 只看正常：异常为需要填写说明或当前不能通过的建议
    anomaly: Literal["all", "abnormal", "normal"] = "all"
    # 按子采购单的供应商筛选；按开票日期筛选（须成对填写）
    supplierId: str = Field(default="", max_length=20, pattern=r"^([1-9][0-9]*)?$")
    invoiceFrom: date | None = Field(default=None, strict=False)
    invoiceTo: date | None = Field(default=None, strict=False)
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def valid_dates(self):
        if bool(self.invoiceFrom) != bool(self.invoiceTo):
            raise ValueError("请同时填写开票开始日期与结束日期")
        if self.invoiceFrom and self.invoiceFrom > self.invoiceTo:
            raise ValueError("开票开始日期不能晚于结束日期")
        return self


class CandidateQuery(StrictModel):
    invoiceId: Id
    invoiceItemId: Id
    keyword: str = Field(default="", max_length=100)


class ReplaceBody(ManualBody):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
