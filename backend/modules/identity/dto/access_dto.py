"""权限管理请求：同步范围、部门默认角色、个人角色。"""

from pydantic import Field

from backend.core.dto import StrictModel


class ScopeSave(StrictModel):
    departmentIds: list[int] = Field(max_length=500)


class RolesSave(StrictModel):
    roles: list[str] = Field(max_length=10)


class UserRolesSave(StrictModel):
    roles: list[str] = Field(max_length=10)
    # 是：只按个人角色授权；否：部门默认角色与个人角色合并
    customRoles: bool
