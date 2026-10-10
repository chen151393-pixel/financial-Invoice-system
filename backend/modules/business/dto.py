"""采购报关联查请求；输入问题由后端处理。"""

import re
from datetime import date
from typing import Literal

from pydantic import Field, StrictBool, field_validator, model_validator
from pydantic_core import PydanticCustomError

from backend.core.dto import StrictModel


class PlScriptQuery(StrictModel):
    """与NS共用脚本的查询输入一致。"""

    type: Literal["pl", "customsRecord", "declaration"] = "pl"
    pl: str = Field(default="", max_length=100)
    month: str = ""
    createdFrom: str = ""
    createdTo: str = ""
    showIncomplete: StrictBool = True

    @field_validator("pl", "month", "createdFrom", "createdTo", mode="before")
    @classmethod
    def trim_input(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_scope(self):
        def invalid(message):
            raise PydanticCustomError("ns_query_scope", message)

        if any(ord(char) < 32 or ord(char) == 127 for char in self.pl):
            invalid("查询单号不能含控制字符")
        if self.month:
            if not re.fullmatch(r"(?:19\d{2}|20\d{2}|2100)-(?:0[1-9]|1[0-2])", self.month):
                invalid("申报月份须为1900至2100年的有效YYYY-MM")
        if bool(self.createdFrom) != bool(self.createdTo):
            invalid("报关单创建日期需同时填写起止值")
        if self.createdFrom:
            for value in (self.createdFrom, self.createdTo):
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    invalid("创建日期须为YYYY-MM-DD")
                try:
                    parsed = date.fromisoformat(value)
                except ValueError:
                    invalid("请填写有效的报关单创建日期")
                if not 1900 <= parsed.year <= 2100:
                    invalid("创建日期年份须在1900至2100年")
            if self.createdFrom > self.createdTo:
                invalid("创建日期起始值不能晚于结束值")
        if not (self.pl or self.month or self.createdFrom):
            invalid("单号、申报月份或完整创建日期范围至少填写一项")
        return self
