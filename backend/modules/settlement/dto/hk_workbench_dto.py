"""香港中转工作区查询；只读，筛选与分页由后端完成。"""

from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from backend.core.dto import StrictModel

from .batch_dto import Number, Text200, amount_value


class HkWorkbenchQuery(StrictModel):
    stage: Literal["open", "register", "collected", "documents_ready", "settled", "cancelled", "all"] = "open"
    consignee: Text200 = ""
    keyword: Text200 = ""
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=10, ge=1, le=50)
    pendingPage: int = Field(default=1, ge=1, le=100000)
    pendingPageSize: int = Field(default=20, ge=1, le=100)


class HkReceiptPreview(StrictModel):
    declarationNos: list[Number] = Field(min_length=1, max_length=200)
    receivedAmount: Decimal = Decimal(0)
    receivedFee: Decimal = Decimal(0)

    @field_validator("receivedAmount", "receivedFee", mode="before")
    @classmethod
    def valid_amount(cls, value):
        return amount_value(value, "金额", allow_zero=True)

    @model_validator(mode="after")
    def unique_numbers(self):
        if len(set(self.declarationNos)) != len(self.declarationNos):
            raise ValueError("请勿重复选择报关单")
        return self
