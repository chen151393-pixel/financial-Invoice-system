"""文件传输边界；仅接收原文件，拒绝客户端提交业务行和租户。"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=5592408)
    previewToken: str | None = Field(default=None, max_length=100)


class InvoiceQuery(BaseModel):
    q: str = Field(default="", max_length=100)
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=20, ge=1, le=100)
    status: Literal["", "normal", "red_offset", "void", "unknown"] = ""
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def valid_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("开始日期不能晚于结束日期")
        return self
