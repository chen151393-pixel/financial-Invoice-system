"""页面授权与成员权限预览请求。"""

from pydantic import Field

from backend.core.dto import StrictModel


class RolePagesSave(StrictModel):
    pages: list[str] = Field(max_length=10)
    revision: int = Field(ge=0)


class UserAccessPreview(StrictModel):
    roles: list[str] = Field(max_length=10)
    customRoles: bool
