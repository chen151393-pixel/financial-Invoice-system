"""海关回执请求：导入原文件（base64）、列表条件与重新匹配范围。"""

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from backend.core.dto import StrictModel
from backend.core.search_terms import SearchText


class CustomsImportRequest(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    # 4MB 原文件的 base64 长度上限
    content: str = Field(min_length=1, max_length=5592408)


class CustomsReceiptQuery(StrictModel):
    # 出口报关单号，多条用逗号、分号或换行分隔，部分匹配
    declarationNo: SearchText = ""
    name: str = Field(default="", max_length=120)
    consignee: str = Field(default="", max_length=120)
    exportFrom: date | None = Field(default=None, strict=False)
    exportTo: date | None = Field(default=None, strict=False)
    # matched 含拆行一致；ns_missing 含 NS 报关单重号
    status: Literal["all", "matched", "different", "ns_missing"] = "all"
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.exportFrom and self.exportTo and self.exportFrom > self.exportTo:
            raise ValueError("出口日期开始不能晚于结束")
        return self


class CustomsRematchRequest(StrictModel):
    # 为空时重新匹配全部回执；给出时只匹配这些回执（最多一页）
    ids: list[int] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def valid_ids(self):
        if any(value < 1 for value in self.ids) or len(set(self.ids)) != len(self.ids):
            raise ValueError("回执 ID 须为不重复的正整数")
        return self
