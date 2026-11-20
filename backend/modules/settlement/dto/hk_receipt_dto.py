"""香港回款独立登记页：选单核对、人工流水登记与严格对平登记。"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import Field, StringConstraints, field_validator, model_validator

from backend.core.dto import StrictModel

from .batch_dto import CreateBatchRequest, Number, amount_value
from .bill_dto import MAX_BILL_BYTES


class BankSlipUpload(StrictModel):
    fileName: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    content: str = Field(min_length=1, max_length=4 * ((MAX_BILL_BYTES + 2) // 3))


class HkRegistrationPreview(StrictModel):
    declarationNos: list[Number] = Field(default_factory=list, max_length=200)
    receivedAmount: Decimal = Decimal(0)
    receivedFee: Decimal = Decimal(0)
    receivedOn: date | None = Field(default=None, strict=False)

    @field_validator("receivedAmount", "receivedFee", mode="before")
    @classmethod
    def valid_amount(cls, value):
        return amount_value(value, "金额", allow_zero=True)

    @model_validator(mode="after")
    def unique_numbers(self):
        if len(self.declarationNos) != len(set(self.declarationNos)):
            raise ValueError("请勿重复选择报关单")
        return self


class RegisterHkReceipt(CreateBatchRequest):
    bankSlip: BankSlipUpload | None = None
