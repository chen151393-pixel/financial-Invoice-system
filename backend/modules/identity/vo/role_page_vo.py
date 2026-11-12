"""角色配置与服务端生效权限预览。"""

from backend.core.dto import StrictModel


class PageItem(StrictModel):
    code: str
    label: str
    group: str
    description: str
    # 普通角色能否分配此页；管理员整个角色固定只读。
    assignable: bool


class RolePages(StrictModel):
    code: str
    label: str
    pages: list[str]
    revision: int
    editable: bool


class RolePageOverview(StrictModel):
    pages: list[PageItem]
    roles: list[RolePages]


class UserAccessPreview(StrictModel):
    version: str
    inheritedRoles: list[str]
    roles: list[str]
    pages: list[PageItem]
    canEnable: bool
    reason: str | None


class UserAccessDetail(StrictModel):
    id: int
    name: str
    departments: list[str]
    personalRoles: list[str]
    customRoles: bool
    enabled: bool
    preview: UserAccessPreview
