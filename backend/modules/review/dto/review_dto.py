"""财务核对请求：列表条件与审核确认；审核只接受报关单内容摘要与备注。"""

from typing import Literal

from pydantic import Field

from backend.core.dto import StrictModel


class DeclarationListQuery(StrictModel):
    keyword: str = Field(default="", max_length=120)
    account: str = Field(default="", max_length=80, pattern=r"^[a-zA-Z0-9_-]*$")
    status: Literal["all", "pending", "approved", "blocked"] = "all"
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=20, ge=1, le=50)


class ApproveRequest(StrictModel):
    contentSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    note: str = Field(default="", max_length=300)
