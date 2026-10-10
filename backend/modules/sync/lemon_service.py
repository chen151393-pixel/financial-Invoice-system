"""柠檬云授权回调接收：仅确认收到请求，不将未经上游核验的 code 当作绑定成功。"""

import secrets
import time
from dataclasses import dataclass, field
from threading import Lock

from backend.core.errors import ApiError
from backend.integrations.lemon.auth import account_authorization_url

CALLBACK_PATH = "/api/lemon/oauth/callback"
CALLBACK_COOKIE = "lemon_callback_context"
AUTHORIZATION_TTL = 600


@dataclass
class PendingAuthorization:
    owner: str
    session_token: str = field(repr=False)
    expires_at: float


class LemonCallbackService:
    def __init__(self, settings, resolve_owner, *, clock=time.monotonic):
        self.settings = settings
        self.resolve_owner = resolve_owner
        self.clock = clock
        self.pending = {}
        self.lock = Lock()

    @property
    def callback_url(self):
        # 使用服务端公开 origin，不相信请求 Host、转发头或前端传入的回调地址。
        return self.settings.origin + CALLBACK_PATH

    def configuration(self):
        allowed = bool(self.settings.lemon_app_id)
        return {
            "callbackUrl": self.callback_url,
            "callbackReady": True,
            "bindingReady": False,
            "authorization": {
                "allowed": allowed,
                "reason": "可发起授权；当前只接收回调，账号绑定尚未接入"
                if allowed
                else "请先在服务器配置 LEMON_OPEN2_APP_KEY",
            },
        }

    def begin(self, owner, session_token, body):
        # 账号关联属于管理员浏览器操作，服务密钥不能代替管理员授权。
        if owner != f"user:{self.settings.admin_user}" or not session_token:
            raise ApiError(403, "请使用管理员浏览器会话发起柠檬云授权")
        if self.resolve_owner(session_token=session_token) != owner:
            raise ApiError(403, "授权发起人与登录身份不匹配")
        if not self.settings.lemon_app_id:
            raise ApiError(503, "请先在服务器配置 LEMON_OPEN2_APP_KEY")
        now = self.clock()
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.pending = {key: value for key, value in self.pending.items() if value.expires_at > now}
            # 同一浏览器只有一个回调 cookie；替换旧上下文，避免不同授权混用。
            self.pending = {
                key: value for key, value in self.pending.items() if value.session_token != session_token
            }
            if len(self.pending) >= 1000:
                raise ApiError(429, "待处理授权过多，请稍后再试")
            self.pending[token] = PendingAuthorization(owner, session_token, now + AUTHORIZATION_TTL)
        return {
            "authorizationUrl": account_authorization_url(
                self.settings.lemon_app_id, body.mobile, self.callback_url
            ),
            "callbackUrl": self.callback_url,
            "expiresIn": AUTHORIZATION_TTL,
            "bindingReady": False,
            "message": "当前仅接收回调；正式账号绑定接通后需要重新授权",
        }, token

    def receive(self, body, context_token):
        if body.code is None:
            return {
                "callbackReady": True,
                "callbackUrl": self.callback_url,
                "callbackReceived": False,
                "accountBound": False,
                "message": "柠檬云回调入口已就绪，请从系统发起授权",
            }
        with self.lock:
            pending = self.pending.pop(context_token, None)
        if pending is None or pending.expires_at <= self.clock():
            raise ApiError(400, "授权上下文缺失、已过期或已使用，请从系统重新发起")
        if self.resolve_owner(session_token=pending.session_token) != pending.owner:
            raise ApiError(403, "授权发起人的会话已失效")
        # 官方只保证回传 code，不保证 state。cookie 只关联浏览器上下文，不证明上游授权有效；
        # 在接入 LinkUser 核验之前不存储 code、不写绑定、不请求 token，也不声称授权成功。
        return {
            "callbackReady": True,
            "callbackReceived": True,
            "accountBound": False,
            "bindingReady": False,
            "message": "已接收授权回调；账号绑定尚未接入，授权码未保存，请在绑定功能上线后重新授权",
        }
