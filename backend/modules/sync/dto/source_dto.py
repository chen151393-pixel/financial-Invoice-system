"""只读拉取的分页边界。"""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

SourceKind = Literal["purchase-orders", "sub-purchase-orders", "customs-declarations"]


class PullCursor(BaseModel):
    """内部 ID 范围内分页；ID 按字符串传输，避免浏览器数字精度损失。"""

    model_config = ConfigDict(extra="forbid")
    afterId: str = Field(pattern=r"^(0|[1-9][0-9]{0,39})$")
    throughId: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,39}$")
    offset: int = Field(default=0, ge=0, strict=True)


class PullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    partialSave: bool = Field(default=False, strict=True)
    progressId: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    offset: int = Field(default=0, ge=0, strict=True)
    cursor: PullCursor | None = None
    limit: int = Field(default=20, ge=1, le=20, strict=True)
    startDate: str = Field(default="", max_length=10)
    endDate: str = Field(default="", max_length=10)
    requireDateRange: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def aligned_page(self):
        if self.requireDateRange and (not self.startDate or not self.endDate):
            raise PydanticCustomError("sync_date_range", "请先填写开始日期和结束日期，再拉取该时间段的数据")
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
        page_offset = self.cursor.offset if self.cursor else self.offset
        if page_offset % self.limit or page_offset // self.limit >= 1000:
            raise ValueError("分页偏移必须与每页数量对齐，且不能超过 1000 页")
        if self.cursor and self.cursor.throughId is not None:
            if int(self.cursor.afterId) >= int(self.cursor.throughId):
                raise ValueError("分页内部 ID 范围无效")
        return self
