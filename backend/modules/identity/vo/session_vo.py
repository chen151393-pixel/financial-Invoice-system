"""会话响应。"""

from backend.core.dto import StrictModel


class RoleItem(StrictModel):
    code: str
    label: str


class SessionUser(StrictModel):
    # feishu 飞书账号；admin 应急管理员；service 服务身份
    kind: str
    name: str
    roles: list[RoleItem]
    canManageAccess: bool


class SessionInfo(StrictModel):
    authenticated: bool
    user: SessionUser | None = None


class LoginOptions(StrictModel):
    feishu: bool
    password: bool


class FeishuStartResult(StrictModel):
    url: str


class FeishuOutcome(StrictModel):
    # none 无记录；pending/checking 进行中；success 已登录；failed 失败
    status: str
    reason: str | None
