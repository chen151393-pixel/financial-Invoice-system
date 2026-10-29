"""发票列表查询（GET 查询参数）。"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class InvoiceQuery(BaseModel):
    q: str = Field(default="", max_length=100)
    invoice_no: str = Field(default="", max_length=100, description="发票号码部分匹配")
    seller_name: str = Field(default="", max_length=100, description="供应商名称部分匹配")
    seller_tax_no: str = Field(default="", max_length=100, description="供应商税号部分匹配")
    account: str = Field(default="", max_length=100, description="来源账套标识；空值查询全部账套")
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=20, ge=1, le=100)
    status: Literal["", "normal", "red_letter", "red_offset", "void", "unknown"] = ""
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def valid_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("开始日期不能晚于结束日期")
        return self
