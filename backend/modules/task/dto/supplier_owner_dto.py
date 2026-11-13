"""供应商人员关联：严格参数、日期、批次与乐观版本。"""

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from backend.core.dto import StrictModel
from backend.core.search_terms import SearchText


class OwnerQuery(StrictModel):
    supplierName: SearchText = ""
    companyId: int | None = Field(default=None, ge=1)
    memberId: int | None = Field(default=None, ge=1)
    status: Literal["all", "assigned", "unassigned", "scheduled"] = "all"
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)


class OwnerPair(StrictModel):
    supplierId: int = Field(ge=1)
    companyId: int = Field(ge=1)
    revision: int = Field(ge=0)


class OwnerChange(StrictModel):
    items: list[OwnerPair] = Field(min_length=1, max_length=100)
    memberId: int = Field(ge=1)
    effectiveDate: date = Field(strict=False)
    reason: str = Field(default="", max_length=300)
    transferOpenTasks: bool = False

    @model_validator(mode="after")
    def unique_pairs(self):
        pairs = {(item.supplierId, item.companyId) for item in self.items}
        if len(pairs) != len(self.items):
            raise ValueError("同一供应商与采购抬头不能重复提交")
        return self


class OwnerSave(OwnerChange):
    previewToken: str = Field(pattern=r"^[0-9a-f]{64}$")
