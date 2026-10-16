"""open2 已有账号绑定协议；不使用授权码换令牌的占位实现。"""

import logging
from urllib.parse import urlencode

import httpx

from backend.core.errors import ApiError

logger = logging.getLogger("lemon.binding")


class LemonExistingAccount:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=20, follow_redirects=False, trust_env=False)

    def close(self):
        self.client.close()

    def authorization_url(self, mobile):
        query = urlencode(
            {
                "appId": self.settings.lemon_app_id,
                "mobile": mobile,
                "redirect_uri": self.settings.lemon_redirect_uri,
            }
        )
        return f"{self.settings.lemon_host}/OAuthPage/OAPage/Index?{query}"

    def _post(self, path, *, body=None, token=None, params=None):
        try:
            response = self.client.post(
                self.settings.lemon_host + path,
                json=body,
                params=params,
                headers={"Authorization": f"Bearer {token}"} if token else {},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            # 不记录 URL、密码、授权码、令牌或上游正文。
            logger.warning("lemon_binding_request_failed type=%s", type(error).__name__)
            raise ApiError(502, "柠檬云响应异常，请核实绑定状态") from None
        if not isinstance(payload, dict) or payload.get("State") not in (1000, 2000, 9999):
            raise ApiError(502, "柠檬云返回格式异常，请核实绑定状态")
        if payload["State"] != 1000:
            raise ApiError(
                400, "柠檬云未确认操作成功，请检查应用配置、账号密码及授权码有效性；已绑定账号可核实状态"
            )
        return payload.get("Data")

    def app_token(self):
        data = self._post(
            "/api/OAuth2/AccessToken/GetAppAccessToken",
            body={
                "appId": int(self.settings.lemon_app_id),
                "appSecret": self.settings.lemon_app_secret,
            },
        )
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("access_token"), str)
            or not data["access_token"]
        ):
            raise ApiError(502, "柠檬云应用授权响应不完整")
        # 低频绑定即时申请；全局 Token 不作为用户 Token，不落盘。
        return data["access_token"]

    def bind(self, token, mobile, code, password):
        result = self._post(
            "/api/OAuth2/LinkUser/LinkUserToApp",
            token=token,
            body={
                "appId": int(self.settings.lemon_app_id),
                "appSecret": self.settings.lemon_app_secret,
                "code": code,
                "mobile": mobile,
                "orgId": 0,
                "userId": mobile,
                "password": password,
            },
        )
        if result is not True:
            raise ApiError(502, "柠檬云未返回明确的绑定成功结果，请核实状态")

    def verify(self, mobile):
        data = self._post(
            "/api/OAuth2/User/GetUserAccountInfo", token=self.app_token(), params={"userId": mobile}
        )
        if not isinstance(data, dict) or data.get("userId") != mobile or data.get("Mobile") != mobile:
            raise ApiError(409, "未核实到当前账号的绑定关系，请联系柠檬云确认，不要重复提交绑定")
