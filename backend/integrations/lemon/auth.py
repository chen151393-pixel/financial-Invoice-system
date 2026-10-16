"""open2 记账开放平台「获取账号授权 → 已有账号」OAuth2 授权码流程。

已实现官方授权页面链接构造；下方保留未接入的 Token 缓存与换取模板，不读取发票业务数据。
模板凭证（app_key/app_secret）来自 config，不写死；退出条件是正式绑定与鉴权适配器接通。

已核实：已有账号授权页面接受 appId、mobile、redirect_uri，回调只保证携带 code。
收到 code 后须获取全局 Token，再调用 LinkUserToApp 绑定，不是标准 OAuth code 换 Token。
当前公开回调只复用 account_authorization_url，尚不调用下方 Token 骨架；
exchange_code、refresh 和 FileTokenStore 均为未接入模板，不能用于生产绑定。
"""

import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Optional
from urllib.parse import urlencode

import httpx

from backend.core.errors import ApiError

from .config import LemonOpen2Settings

logger = logging.getLogger("lemon.open2.auth")


def log_failure(operation, error_type, status=None):
    # 不输出 URL、token、请求/响应正文，避免凭据与业务数据进入日志。
    logger.error(
        "lemon_auth_failed operation=%s upstream_status=%s type=%s",
        operation,
        status if status is not None else "-",
        error_type,
    )


@dataclass
class Token:
    access_token: str
    refresh_token: str
    expires_at: float  #  monotonic 秒，过期时刻


class TokenStore:
    """token 持久化抽象；sync 模块可替换为加密存储或数据库实现。"""

    def load(self) -> Optional[Token]:
        raise NotImplementedError

    def save(self, token: Token) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


class FileTokenStore(TokenStore):
    """骨架用：明文落盘，仅供本地联调。生产必须替换为加密存储/数据库，且限制文件权限。"""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Optional[Token]:
        if not self.path or not self.path.is_file():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return Token(
                access_token=str(data["access_token"]),
                refresh_token=str(data["refresh_token"]),
                expires_at=float(data["expires_at"]),
            )
        except (ValueError, KeyError, OSError):
            log_failure("token_load", "InvalidTokenFile")
            return None

    def save(self, token: Token) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "access_token": token.access_token,
                    "refresh_token": token.refresh_token,
                    "expires_at": token.expires_at,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def clear(self) -> None:
        if self.path and self.path.is_file():
            self.path.unlink()


def account_authorization_url(
    app_id: str, mobile: str, redirect_uri: str, *, host: str = "https://open2.ningmengyun.com"
) -> str:
    """官方已有账号授权页面只约定 appId、mobile、redirect_uri，后者必须 URL 编码。"""
    return (
        host.rstrip("/")
        + "/OAuthPage/OAPage/Index?"
        + urlencode(
            {
                "appId": app_id,
                "mobile": mobile,
                "redirect_uri": redirect_uri,
            }
        )
    )


class LemonOpen2Auth:
    def __init__(
        self, settings: LemonOpen2Settings, store: TokenStore, client: Optional[httpx.Client] = None
    ):
        self.settings = settings
        self.store = store
        self.client = client or httpx.Client(timeout=20, follow_redirects=False, trust_env=False)
        self._cached: Optional[Token] = None
        self._lock = Lock()

    def close(self):
        self.client.close()

    def authorize_url(self, mobile: str) -> str:
        """复用官方已有账号授权页面；不假定平台回传 state。"""
        return account_authorization_url(
            self.settings.app_key, mobile, self.settings.redirect_uri, host=self.settings.api_base
        )

    def exchange_code(self, code: str, state: str) -> Token:
        """授权回调拿到 code 后换取 token。state 校验由调用方在路由层完成。"""
        token = self._request_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.settings.redirect_uri,
                "client_id": self.settings.app_key,
                "client_secret": self.settings.app_secret,
            }
        )
        self._persist(token)
        return token

    def refresh(self, refresh_token: str) -> Token:
        token = self._request_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.settings.app_key,
                "client_secret": self.settings.app_secret,
            }
        )
        self._persist(token)
        return token

    def _request_token(self, body: dict) -> Token:
        try:
            response = self.client.post(self.settings.token_url, data=body, follow_redirects=False)
        except httpx.HTTPError as error:
            log_failure("token", type(error).__name__)
            raise ApiError(502, "柠檬云 open2 Token 请求失败或超时") from None
        if not response.is_success:
            log_failure("token", "HTTPStatusError", response.status_code)
            raise ApiError(502, f"柠檬云 open2 认证失败（HTTP {response.status_code}）")
        try:
            data = response.json()
            access = data["access_token"]
            refresh = data.get("refresh_token", "")
            expiry = float(data.get("expires_in", 7200))
            if not isinstance(access, str) or not access or not math.isfinite(expiry) or expiry <= 0:
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            log_failure("token", "InvalidTokenResponse", response.status_code)
            raise ApiError(502, "柠檬云 open2 Token 响应不完整") from None
        # 提前 60s 视为过期，避免临界点失效。
        return Token(access_token=access, refresh_token=refresh, expires_at=time.monotonic() + expiry - 60)

    def _persist(self, token: Token) -> None:
        with self._lock:
            self._cached = token
        try:
            self.store.save(token)
        except OSError:
            log_failure("token_save", "OSError")

    def token(self) -> str:
        """返回可用的 access_token；过期则用 refresh_token 续期；都没有则提示先授权。"""
        with self._lock:
            cached = self._cached or self.store.load()
            if cached and cached.expires_at > time.monotonic():
                self._cached = cached
                return cached.access_token
            if cached and cached.refresh_token:
                try:
                    renewed = self.refresh(cached.refresh_token)
                except ApiError:
                    log_failure("token", "RefreshFailed")
                    raise ApiError(503, "柠檬云 open2 刷新失败，请重新走已有账号授权") from None
                return renewed.access_token
        raise ApiError(503, "柠檬云 open2 尚未完成账号授权，请先走授权回调换取 token")
