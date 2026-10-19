"""工作台查询条件；统计遵循账套，搜索与分类仅作用于待办。"""

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from backend.core.dto import StrictModel


class WorkbenchQuery(StrictModel):
    account: str = Field(default="", max_length=100)
    keyword: str = Field(default="", max_length=120)
    kind: Literal["all", "review", "matching", "task"] = "all"
    sort: Literal["priority", "oldest", "newest"] = "priority"
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=5, ge=1, le=50)
    trendStart: date | None = Field(default=None, strict=False)
    trendEnd: date | None = Field(default=None, strict=False)

    @model_validator(mode="after")
    def valid_trend_dates(self):
        if bool(self.trendStart) != bool(self.trendEnd):
            raise ValueError("请同时填写开票开始日期与结束日期")
        if self.trendStart and self.trendEnd:
            if self.trendStart > self.trendEnd:
                raise ValueError("开票开始日期不能晚于结束日期")
            if (self.trendEnd - self.trendStart).days > 91:
                raise ValueError("开票趋势单次最多查询 92 天")
        return self
