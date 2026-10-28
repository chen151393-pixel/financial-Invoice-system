"""会话与身份：应急管理员账号密码登录、飞书登录签发会话、每次请求的身份校验。

会话仍在 API 进程内存中（单进程部署约束不变）；飞书人员每次请求按数据库校验在职与角色，
停用或收回全部角色后下一次请求立即失效。
"""

import hashlib
import hmac
import secrets
import time
from threading import Lock

from backend.core.errors import ApiError

from ..policy.login_policy import feishu_user_id
from ..policy.role_policy import EMERGENCY_ROLES, ROLES, can_manage_access

SESSION_SECONDS = 8 * 3600


def same(left: str, right: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(left.encode()).digest(), hashlib.sha256(right.encode()).digest()
    )


class IdentityService:
    def __init__(self, settings, access=None):
        self.settings = settings
        self.access = access
        self.sessions = {}
        self.attempts = {}
        self.lock = Lock()

    def check_origin(self, origin):
        if origin != self.settings.origin:
            raise ApiError(403, "请求来源不匹配")

    def _issue_session(self, session_token, now, actor):
        """调用方持有self.lock。"""
        self.sessions = {key: value for key, value in self.sessions.items() if value[1] > now}
        self.sessions.pop(session_token, None)
        if len(self.sessions) >= 1000:
            self.sessions.pop(next(iter(self.sessions)))
        token = secrets.token_hex(32)
        self.sessions[token] = (actor, now + SESSION_SECONDS)
        return token

    def issue(self, actor, session_token=None):
        """飞书登录校验通过后签发会话；调用方已完成全部资格校验。"""
        with self.lock:
            return self._issue_session(session_token, time.monotonic(), actor)

    def open_local_session(self, *, origin, ip, host, session_token=None):
        """旧客户端兼容入口；账号密码登录启用后不再签发免密会话。"""
        self.check_origin(origin)
        raise ApiError(403, "请使用账号和密码登录")

    def login(self, username, password, *, origin, ip, session_token=None):
        self.check_origin(origin)
        if not self.settings.admin_password_login:
            raise ApiError(403, "管理员账号密码登录已关闭，请使用飞书登录")
        if not self.settings.admin_password:
            raise ApiError(503, "请在服务器配置非空的 ADMIN_PASSWORD")
        now = time.monotonic()
        with self.lock:
            self.sessions = {key: value for key, value in self.sessions.items() if value[1] > now}
            self.attempts = {key: value for key, value in self.attempts.items() if value[1] > now}
            count, until = self.attempts.get(ip, (0, now + 900))
            if count >= 10:
                raise ApiError(429, "登录尝试过多，请稍后再试")
            if not (
                same(username, self.settings.admin_user) and same(password, self.settings.admin_password)
            ):
                if len(self.attempts) >= 1000 and ip not in self.attempts:
                    raise ApiError(429, "登录尝试过多，请稍后再试")
                self.attempts[ip] = (count + 1, until)
                raise ApiError(401, "用户名或密码错误")
            self.attempts.pop(ip, None)
            return self._issue_session(session_token, now, f"user:{self.settings.admin_user}")

    def owner(self, *, authorization="", session_token=None, method="GET", origin=None):
        if (
            len(self.settings.service_key) >= 32
            and authorization.startswith("Bearer ")
            and same(authorization[7:], self.settings.service_key)
        ):
            return "service:feishu"
        with self.lock:
            session = self.sessions.get(session_token)
        if not session or session[1] <= time.monotonic():
            raise ApiError(401, "请先登录")
        if method not in ("GET", "HEAD"):
            self.check_origin(origin)
        user_id = feishu_user_id(session[0])
        if user_id is not None and not self._feishu_allowed(user_id):
            with self.lock:
                self.sessions.pop(session_token, None)
            raise ApiError(401, "账号已停用或权限已收回，请重新登录")
        return session[0]

    def _feishu_allowed(self, user_id):
        if self.access is None:
            return False
        user, roles = self.access.current(user_id)
        return bool(user and user["active"] and roles)

    def roles_of(self, actor):
        """当前生效角色代码；服务身份没有角色。"""
        if actor == f"user:{self.settings.admin_user}":
            return list(EMERGENCY_ROLES)
        user_id = feishu_user_id(actor)
        if user_id is None or self.access is None:
            return []
        user, roles = self.access.current(user_id)
        return roles if user and user["active"] else []

    def describe(self, actor):
        """GET /api/session 的当前身份说明；只含展示所需字段。"""
        user_id = feishu_user_id(actor)
        if user_id is not None and self.access is not None:
            user, roles = self.access.current(user_id)
            name, kind = (user["name"] if user else user_id), "feishu"
        elif actor == f"user:{self.settings.admin_user}":
            name, kind, roles = "管理员（应急账号）", "admin", list(EMERGENCY_ROLES)
        else:
            name, kind, roles = actor, "service", []
        return {
            "kind": kind,
            "name": name,
            "roles": [{"code": code, "label": ROLES[code]} for code in roles],
            "canManageAccess": can_manage_access(roles),
        }

    def require_manage(self, actor):
        if not can_manage_access(self.roles_of(actor)):
            raise ApiError(403, "需要系统管理员角色才能管理人员与权限")

    def logout(self, session_token):
        with self.lock:
            self.sessions.pop(session_token, None)
