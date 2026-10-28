"""飞书开放平台只读接口：网页授权换取登录身份、通讯录部门与成员。

凭证和令牌只保存在服务端内存；用户令牌只用于读取一次身份，不缓存。
接口地址按 2026-10 飞书开放平台文档核对：
- 授权页 accounts.feishu.cn/open-apis/authen/v1/authorize
- 授权码换 user_access_token：/open-apis/authen/v2/oauth/token
- 当前用户：/open-apis/authen/v1/user_info
- 应用令牌：/open-apis/auth/v3/tenant_access_token/internal
- 通讯录：/open-apis/contact/v3/scopes、departments/{id}、departments/{id}/children、users/find_by_department
"""

import json
import time
from threading import Lock
from urllib.parse import quote, urlencode

import httpx

from backend.core.errors import ApiError

OPEN_URL = "https://open.feishu.cn/open-apis/"
AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
MAX_PAGES = 200


class FeishuError(ApiError):
    def __init__(self, code, message):
        super().__init__(502, message)
        self.code = code


REASONS = {
    99991663: "飞书应用令牌无效，请检查 App ID 与 App Secret",
    99991664: "飞书应用令牌无效，请检查 App ID 与 App Secret",
    99991668: "飞书用户令牌无效，请重新登录",
    99991672: "飞书应用缺少通讯录权限，请在开放平台申请并发布版本",
    99991679: "飞书应用缺少用户授权的权限，请在开放平台申请并发布版本",
    40004: "飞书应用无权读取该部门，请检查通讯录权限范围",
    40014: "飞书应用无权读取该部门，请检查通讯录权限范围",
    43010: "部门过大，无法一次读取全部下级部门",
    20003: "飞书授权码无效，请重新登录",
    20004: "飞书授权码已过期或已使用，请重新登录",
    20024: "飞书授权码与应用不匹配，请检查 App ID",
}


class FeishuClient:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=20, follow_redirects=False, trust_env=False)
        self._tenant = None
        self._lock = Lock()

    def close(self):
        self.client.close()

    @property
    def configured(self):
        return bool(self.settings.feishu_app_id and self.settings.feishu_app_secret)

    def _require(self):
        if not self.configured:
            raise ApiError(503, "飞书登录尚未配置，请管理员填写 FEISHU_APP_ID 与 FEISHU_APP_SECRET")

    def authorize_url(self, state):
        self._require()
        query = urlencode(
            {
                "client_id": self.settings.feishu_app_id,
                "response_type": "code",
                "redirect_uri": self.settings.feishu_redirect_uri,
                "state": state,
            },
            quote_via=quote,
        )
        return f"{AUTHORIZE_URL}?{query}"

    def _request(self, method, path, *, token=None, params=None, body=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            response = self.client.request(method, OPEN_URL + path, params=params, json=body, headers=headers)
            if len(response.content) > 8 * 1024 * 1024:
                raise ApiError(502, "飞书返回数据过大，请缩小同步范围")
            data = json.loads(response.content)
        except httpx.HTTPError:
            raise ApiError(502, "无法连接飞书，请检查网络后重试") from None
        except (ValueError, UnicodeError):
            raise ApiError(502, "飞书返回的数据格式异常，请稍后重试") from None
        if not isinstance(data, dict) or type(data.get("code")) is not int:
            raise ApiError(502, f"飞书接口调用失败（HTTP {response.status_code}），请稍后重试")
        code = data["code"]
        if code != 0:
            # 不回传 msg 原文，其中可能带有请求参数。
            raise FeishuError(
                code, f"飞书接口调用失败（{code}）：{REASONS.get(code, '请检查飞书应用配置与权限')}"
            )
        return data

    def exchange_code(self, code):
        """授权码换取 user_access_token；授权码 5 分钟内有效且只能使用一次。"""
        self._require()
        data = self._request(
            "POST",
            "authen/v2/oauth/token",
            body={
                "grant_type": "authorization_code",
                "client_id": self.settings.feishu_app_id,
                "client_secret": self.settings.feishu_app_secret,
                "code": code,
                "redirect_uri": self.settings.feishu_redirect_uri,
            },
        )
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise ApiError(502, "飞书未返回用户令牌，请重新登录")
        return token

    def user_info(self, user_token):
        data = self._request("GET", "authen/v1/user_info", token=user_token).get("data")
        if not isinstance(data, dict):
            raise ApiError(502, "飞书返回的用户信息格式异常")
        return data

    def _tenant_token(self):
        self._require()
        with self._lock:
            if self._tenant and self._tenant[1] > time.monotonic():
                return self._tenant[0]
            data = self._request(
                "POST",
                "auth/v3/tenant_access_token/internal",
                body={"app_id": self.settings.feishu_app_id, "app_secret": self.settings.feishu_app_secret},
            )
            token, expire = data.get("tenant_access_token"), data.get("expire")
            if not isinstance(token, str) or not token or type(expire) is not int or expire <= 0:
                raise ApiError(502, "飞书返回的应用令牌格式异常")
            self._tenant = token, time.monotonic() + max(1, expire - 300)
            return token

    def _pages(self, path, params, key):
        params = {**params, "page_size": 50}
        items = []
        for _ in range(MAX_PAGES):
            data = self._request("GET", path, token=self._tenant_token(), params=params).get("data")
            if not isinstance(data, dict):
                raise ApiError(502, "飞书返回的分页数据缺失，未能读取完整列表")
            page = data.get(key) or []
            if not isinstance(page, list):
                raise ApiError(502, "飞书返回的列表格式异常")
            items.extend(page)
            if not data.get("has_more"):
                return items
            token = data.get("page_token")
            if not isinstance(token, str) or not token:
                raise ApiError(502, "飞书分页标记缺失，未能读取完整列表")
            params = {**params, "page_token": token}
        raise ApiError(502, "飞书列表页数过多，请缩小同步范围")

    def scope_department_ids(self):
        """应用通讯录权限范围内直接授权的部门。"""
        return self._pages(
            "contact/v3/scopes", {"department_id_type": "open_department_id"}, "department_ids"
        )

    def department(self, open_department_id):
        data = self._request(
            "GET",
            f"contact/v3/departments/{quote(open_department_id, safe='')}",
            token=self._tenant_token(),
            params={"department_id_type": "open_department_id"},
        ).get("data")
        department = (data or {}).get("department")
        if not isinstance(department, dict):
            raise ApiError(502, "飞书返回的部门信息格式异常")
        return department

    def child_departments(self, open_department_id, *, recursive=True):
        """下级部门；非递归模式用于从直属关系还原组织树。"""
        return self._pages(
            f"contact/v3/departments/{quote(open_department_id, safe='')}/children",
            {"department_id_type": "open_department_id", "fetch_child": "true" if recursive else "false"},
            "items",
        )

    def department_users(self, open_department_id):
        """部门直属成员；下级部门成员需对下级部门分别读取。"""
        return self._pages(
            "contact/v3/users/find_by_department",
            {
                "department_id": open_department_id,
                "department_id_type": "open_department_id",
                "user_id_type": "user_id",
            },
            "items",
        )
