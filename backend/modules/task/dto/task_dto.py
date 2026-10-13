"""开票任务列表查询。"""

from typing import Literal

from pydantic import Field

from backend.core.dto import StrictModel


class TaskListQuery(StrictModel):
    keyword: str = Field(default="", max_length=120)
    account: str = Field(default="", max_length=100, pattern=r"^[a-zA-Z0-9_-]*$")
    groupBy: Literal["supplier", "declaration"] = "supplier"
    status: Literal["current", "superseded", "all"] = "current"
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)
