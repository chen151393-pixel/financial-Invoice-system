"""记录查询请求；空目标等输入问题由后端处理。"""

from typing import Literal

from pydantic import Field, field_validator

from backend.core.dto import StrictModel


class RecordQuery(StrictModel):
    type: str = Field(max_length=100)
    id: str = Field(default="", max_length=140)
    mode: Literal["list", "detail"]


class PlQuery(StrictModel):
    pl: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    page: int = Field(default=1, ge=1, le=12)


class PlSyncRequest(StrictModel):
    pl: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class LocalPlQuery(PlSyncRequest):
    page: int = Field(default=1, ge=1, le=100000)


class PlComparisonQuery(StrictModel):
    pl: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    company: str = Field(default="", max_length=120)

    @field_validator("pl", "company", mode="before")
    @classmethod
    def strip_search_input(cls, value):
        return value.strip() if isinstance(value, str) else value
