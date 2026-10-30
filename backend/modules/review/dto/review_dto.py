"""财务核对请求：列表条件与审核确认（单张、批量）；审核只接受报关单内容摘要与备注。"""

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from backend.core.dto import StrictModel
from backend.core.search_terms import SearchText


class DeclarationListQuery(StrictModel):
    createdFrom: date | None = Field(default=None, strict=False)
    createdTo: date | None = Field(default=None, strict=False)
    supplierName: SearchText = ""
    recordNo: SearchText = ""
    purchaseOrderNo: SearchText = ""
    keyword: str = Field(default="", max_length=120)
    account: str = Field(default="", max_length=80, pattern=r"^[a-zA-Z0-9_-]*$")
    # margin_alert：待审核且申报幅度异常；auto：待审核且满足可自动审核条件
    status: Literal["all", "pending", "approved", "margin_alert", "auto"] = "all"
    supplierId: str = Field(default="", max_length=20, pattern=r"^([1-9][0-9]*)?$")
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def valid_created_dates(self):
        if bool(self.createdFrom) != bool(self.createdTo):
            raise ValueError("请同时填写报关单创建开始日期与结束日期")
        if self.createdFrom and self.createdFrom > self.createdTo:
            raise ValueError("报关单创建开始日期不能晚于结束日期")
        if self.createdFrom == date.min or self.createdTo == date.max:
            raise ValueError("报关单创建日期超出支持范围")
        return self


class CurrencyEvidence(StrictModel):
    purchaseOrderId: str = Field(pattern=r"^[1-9][0-9]*$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    reference: str = Field(min_length=1, max_length=500)
    note: str = Field(min_length=1, max_length=300)

    @field_validator("reference", "note")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("核实证据和说明不能为空")
        return value.strip()


class ApproveRequest(StrictModel):
    contentSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    note: str = Field(default="", max_length=300)

    currencyEvidence: list[CurrencyEvidence] = Field(default_factory=list, max_length=300)


class BatchApproveItem(StrictModel):
    id: str = Field(pattern=r"^[1-9][0-9]*$")
    contentSha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BatchApproveRequest(StrictModel):
    """批量审核：只提交页面上核对过的报关单 ID 与当时的内容摘要；一次最多一页（50 张）。"""

    items: list[BatchApproveItem] = Field(min_length=1, max_length=50)
    note: str = Field(default="", max_length=300)

    @field_validator("items")
    @classmethod
    def unique(cls, value):
        if len({item.id for item in value}) != len(value):
            raise ValueError("同一张报关单不能重复提交")
        return value
