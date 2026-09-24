"""审核请求只接受服务器快照身份及备注。"""

from typing import Literal

from pydantic import Field

from backend.core.dto import StrictModel
from backend.modules.business.public import PlScriptQuery


class ReviewQuery(StrictModel):
    criteria: PlScriptQuery
    status: Literal["all", "pending", "approved", "blocked"] = "all"


class DeclarationListQuery(StrictModel):
    keyword: str = Field(default="", max_length=120)
    account: str = Field(default="", max_length=80, pattern=r"^[a-zA-Z0-9_-]*$")
    status: Literal["all", "pending", "approved", "blocked"] = "all"
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)


class ApproveRequest(StrictModel):
    snapshotId: str = Field(pattern=r"^[0-9a-f-]{36}$")
    note: str = Field(default="", max_length=300)


class TaskListQuery(StrictModel):
    keyword: str = Field(default="", max_length=120)
    account: str = Field(default="", max_length=100, pattern=r"^[a-zA-Z0-9_-]*$")
    groupBy: Literal["supplier", "declaration"] = "supplier"
    status: Literal["current", "superseded", "all"] = "current"
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)
