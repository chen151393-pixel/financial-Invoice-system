"""发票统计查询：与发票列表相同的筛选条件，不接收页码或前端金额。"""

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from backend.core.dto import StrictModel


class InvoiceTotalsQuery(StrictModel):
    q: str = Field(default="", max_length=100)
    account: str = Field(default="", max_length=100, description="与发票列表相同的来源账套标识")
    status: Literal["", "normal", "red_letter", "red_offset", "void", "unknown"] = ""
    date_from: date | None = Field(default=None, strict=False)
    date_to: date | None = Field(default=None, strict=False)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("开始日期不能晚于结束日期")
        return self
