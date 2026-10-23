"""工作台查询条件；统计遵循账套，搜索与分类仅作用于待办。"""

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from backend.core.dto import StrictModel


class WorkbenchQuery(StrictModel):
    account: str = Field(default="", max_length=100)
    supplierId: str = Field(default="", max_length=20, pattern=r"^([1-9][0-9]*)?$")
    # 报关单创建日期（NS 创建时间的中国日期），须成对填写；作用于分区计数与核对、开票待办
    createdFrom: date | None = Field(default=None, strict=False)
    createdTo: date | None = Field(default=None, strict=False)
    keyword: str = Field(default="", max_length=120)
    kind: Literal["all", "review", "matching", "task"] = "all"
    sort: Literal["priority", "oldest", "newest"] = "priority"
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=5, ge=1, le=50)
    trendStart: date | None = Field(default=None, strict=False)
    trendEnd: date | None = Field(default=None, strict=False)

    @model_validator(mode="after")
    def valid_created_dates(self):
        if bool(self.createdFrom) != bool(self.createdTo):
            raise ValueError("请同时填写报关单创建开始日期与结束日期")
        if self.createdFrom and self.createdFrom > self.createdTo:
            raise ValueError("报关单创建开始日期不能晚于结束日期")
        return self

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
