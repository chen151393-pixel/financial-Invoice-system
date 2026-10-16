"""开票任务列表查询。"""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from backend.core.dto import StrictModel


class TaskListQuery(StrictModel):
    keyword: str = Field(default="", max_length=120)
    account: str = Field(default="", max_length=100, pattern=r"^[a-zA-Z0-9_-]*$")
    groupBy: Literal["supplier", "declaration"] = "supplier"
    status: Literal["current", "superseded", "all"] = "current"
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)


class ClosureRequest(StrictModel):
    requestId: UUID = Field(strict=False)
    purchaseBasisId: str = Field(pattern=r"^[1-9][0-9]*$")
    ledgerSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=300)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("差异结束说明不能为空")
        return value.strip()
