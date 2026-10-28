"""权限管理页响应。"""

from backend.core.dto import StrictModel

from .session_vo import RoleItem


class DepartmentItem(StrictModel):
    id: int
    openDepartmentId: str
    name: str
    path: str
    # 是否被直接选为同步范围；covered 表示因上级部门被选中而在范围内
    inScope: bool
    covered: bool
    roles: list[str]


class UserItem(StrictModel):
    id: int
    name: str
    departments: list[str]
    active: bool
    enabled: bool
    directoryActive: bool
    inactiveReason: str | None
    customRoles: bool
    personalRoles: list[str]
    roles: list[str]
    # UTC 时间，ISO 8601 带 Z
    lastLoginAt: str | None


class SyncRun(StrictModel):
    id: int
    trigger: str
    status: str
    departments: int
    usersAdded: int
    usersUpdated: int
    usersDeactivated: int
    error: str | None
    startedAt: str
    finishedAt: str | None


class AccessOverview(StrictModel):
    feishuConfigured: bool
    roles: list[RoleItem]
    departments: list[DepartmentItem]
    # 本部门或下级部门有已导入员工；包含未启用、已停用账号，与人员列表口径一致。
    importedDepartments: list[DepartmentItem]
    users: list[UserItem]
    lastSync: SyncRun | None


class UserList(StrictModel):
    items: list[UserItem]
    total: int
    page: int
    pageSize: int
    pageCount: int
