"""飞书组织预览、范围确认与成员查询请求。"""

from pydantic import Field

from backend.core.dto import StrictModel


class DirectorySelection(StrictModel):
    departmentIds: list[str] = Field(default_factory=list, max_length=500)
    userIds: list[str] = Field(default_factory=list, max_length=5000)


class DirectoryMemberQuery(DirectorySelection):
    departmentId: str = Field(max_length=64)
    query: str = Field(default="", max_length=100)
    page: int = Field(default=1, ge=1)


class UserAccessSave(StrictModel):
    roles: list[str] = Field(max_length=10)
    customRoles: bool
    enabled: bool
