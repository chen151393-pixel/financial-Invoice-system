"""群配置入口校验；供应商归属与版本在服务层重新核对。"""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from backend.core.dto import StrictModel

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Identity = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=190)]
WecomId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=190, pattern=r"^[A-Za-z0-9_@.\-]+$"),
]


class GroupQuery(StrictModel):
    keyword: str = Field(default="", max_length=120)
    account: str = Field(default="", max_length=100)
    status: Literal["all", "enabled", "disabled"] = "all"
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=20, ge=1, le=50)


class GroupFields(StrictModel):
    groupName: Name
    chatId: WecomId
    employee: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    userid: WecomId


class GroupSave(StrictModel):
    chatId: WecomId
    account: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    supplierId: Identity
    revision: int = Field(ge=0)
    enabled: bool = True


class WecomGroupQuery(StrictModel):
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=20, ge=1, le=50)
    refresh: bool = False
