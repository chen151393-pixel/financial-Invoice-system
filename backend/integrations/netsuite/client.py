"""NS HTTP适配器：认证缓存、读写与传输约束。"""

import math
import re
import time
from threading import Lock
from urllib.parse import quote

import httpx

from backend.core.config import Settings
from backend.core.errors import ApiError

from .auth import assertion


class NetSuite:
    def __init__(self, settings: Settings, client=None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False)
        self._cached = None
        self._lock = Lock()

    def close(self):
        self.client.close()

    def token(self):
        with self._lock:
            if self._cached and self._cached[1] > time.monotonic() + 60:
                return self._cached[0]
            c = self.settings
            if c.missing():
                raise ApiError(503, "NS 配置不完整，请检查连接状态")
            try:
                signed = assertion(c, c.private_key.read_bytes())
            except OSError:
                raise ApiError(503, "无法读取 NS 私钥") from None
            try:
                response = self.client.post(
                    c.token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                        "client_assertion": signed,
                    },
                    timeout=20,
                    follow_redirects=False,
                )
            except httpx.HTTPError:
                raise ApiError(502, "NS Token 请求失败或超时") from None
            if not response.is_success:
                raise ApiError(502, f"NS 认证失败（HTTP {response.status_code}），请检查证书映射和权限")
            try:
                data = response.json()
                value, expiry = data["access_token"], float(data["expires_in"])
                if not isinstance(value, str) or not value or not math.isfinite(expiry) or expiry <= 0:
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise ApiError(502, "NS Token 响应不完整") from None
            self._cached = value, time.monotonic() + expiry
            return value

    def validate(self, record_type, record_id=None):
        if (
            not isinstance(record_type, str)
            or record_type not in self.settings.record_types
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,99}", record_type)
        ):
            raise ApiError(400, "该 NS 记录类型未获准访问")
        if record_id is not None and (
            not isinstance(record_id, str)
            or not re.fullmatch(r"(?:[0-9]{1,40}|eid:[A-Za-z0-9_-]{1,100})", record_id)
        ):
            raise ApiError(400, "NS 记录 ID 格式错误")

    def request(self, method, record_type, record_id=None, payload=None, token=None):
        self.validate(record_type, record_id)
        if method not in ("GET", "POST", "PATCH"):
            raise ApiError(400, "不支持的 NS 操作")
        url = f"{self.settings.record_url}/{record_type}"
        if record_id is not None:
            url += "/" + quote(record_id, safe="")
        params = {"expandSubResources": "true"} if record_id else {"limit": "50"}
        access_token = token or self.token()
        try:
            response = self.client.request(
                method,
                url,
                params=params if method == "GET" else None,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                **({"json": payload} if payload is not None else {}),
                follow_redirects=False,
            )
        except httpx.HTTPError:
            raise ApiError(502, "NS 请求失败或超时；写入结果可能需要人工核对") from None
        if response.status_code == 401:
            with self._lock:
                if self._cached and self._cached[0] == access_token:
                    self._cached = None
        if not response.is_success:
            raise ApiError(
                404 if response.status_code == 404 else 502,
                f"NS 请求未成功（HTTP {response.status_code}）；请核对 NS 权限和字段",
            )
        try:
            data = response.json() if response.content else None
        except ValueError:
            raise ApiError(502, "NS 返回非 JSON 响应") from None
        return {"data": data, "location": response.headers.get("location"), "status": response.status_code}
