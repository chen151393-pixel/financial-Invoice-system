"""只读拉取的分页边界。"""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

SourceKind = Literal["purchase-orders", "sub-purchase-orders", "customs-declarations"]


class LemonAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mobile: str = Field(pattern=r"^1[0-9]{10}$", strict=True)


class LemonCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, min_length=1, max_length=2048, pattern=r"^[^\s\x00-\x1f\x7f]+$")


class PullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset: int = Field(default=0, ge=0, le=99980, strict=True)
    limit: int = Field(default=20, ge=1, le=20, strict=True)
    startDate: str = Field(default="", max_length=10)
    endDate: str = Field(default="", max_length=10)

    @model_validator(mode="after")
    def aligned_page(self):
        if bool(self.startDate) != bool(self.endDate):
            raise PydanticCustomError("sync_date_range", "请同时填写开始日期和结束日期")
        for value in (self.startDate, self.endDate):
            if not value:
                continue
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                raise PydanticCustomError("sync_date_range", "请填写有效日期，格式为 YYYY-MM-DD") from None
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) or not 1900 <= parsed.year <= 2100:
                raise PydanticCustomError("sync_date_range", "日期须为 1900 至 2100 年的 YYYY-MM-DD")
        if self.startDate > self.endDate:
            raise PydanticCustomError("sync_date_range", "开始日期不能晚于结束日期")
        if self.offset % self.limit or self.offset // self.limit >= 1000:
            raise ValueError("分页偏移必须与每页数量对齐，且不能超过 1000 页")
        return self
