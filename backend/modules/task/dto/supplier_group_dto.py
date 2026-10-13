"""供应商群配置入口校验；供应商是否存在与版本在服务层核对。"""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from backend.core.dto import StrictModel

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
WecomId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=190, pattern=r"^[A-Za-z0-9_@.\-]+$"),
]
SupplierId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[1-9][0-9]{0,18}$")]


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
    supplierId: SupplierId
    revision: int = Field(ge=0, description="当前配置版本，新增时为 0")
    enabled: bool = True


class WecomGroupQuery(StrictModel):
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=20, ge=1, le=50)
    refresh: bool = False
