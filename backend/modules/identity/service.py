"""单管理员身份与内存会话；保持单API进程部署约束。"""

import hashlib
import hmac
import ipaddress
import secrets
import time
from threading import Lock
from urllib.parse import urlsplit

from backend.core.errors import ApiError


def same(left: str, right: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(left.encode()).digest(), hashlib.sha256(right.encode()).digest()
    )


class IdentityService:
    def __init__(self, settings):
        self.settings = settings
        self.sessions = {}
        self.attempts = {}
        self.lock = Lock()

    def check_origin(self, origin):
        if origin != self.settings.origin:
            raise ApiError(403, "请求来源不匹配")

    def _issue_session(self, session_token, now):
        """调用方持有self.lock；沿用原管理员owner，避免免登录后数据归属变化。"""
        self.sessions = {key: value for key, value in self.sessions.items() if value[1] > now}
        self.sessions.pop(session_token, None)
        if len(self.sessions) >= 1000:
            self.sessions.pop(next(iter(self.sessions)))
        token = secrets.token_hex(32)
        self.sessions[token] = (f"user:{self.settings.admin_user}", now + 8 * 3600)
        return token

    def open_local_session(self, *, origin, ip, host, session_token=None):
        if not self.settings.local_browser_access:
            raise ApiError(403, "本机直接进入尚未启用，请在服务器配置LOCAL_BROWSER_ACCESS=true")
        self.check_origin(origin)
        configured = urlsplit(self.settings.origin)
        if (
            configured.hostname not in ("localhost", "127.0.0.1", "::1")
            or self.settings.host not in ("localhost", "127.0.0.1", "::1")
            or host != configured.netloc
        ):
            raise ApiError(403, "该入口只允许本机浏览器访问")
        try:
            local = ipaddress.ip_address(ip).is_loopback
        except ValueError:
            local = False
        if not local:
            raise ApiError(403, "该入口只允许本机浏览器访问")
        with self.lock:
            return self._issue_session(session_token, time.monotonic())

    def login(self, username, password, *, origin, ip, session_token=None):
        self.check_origin(origin)
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
            return self._issue_session(session_token, now)

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
            raise ApiError(
                401,
                "本机会话已失效，请刷新页面重新进入" if self.settings.local_browser_access else "请先登录",
            )
        if method not in ("GET", "HEAD"):
            self.check_origin(origin)
        return session[0]

    def logout(self, session_token):
        with self.lock:
            self.sessions.pop(session_token, None)
