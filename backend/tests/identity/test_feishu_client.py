"""飞书适配器：请求地址、参数、分页、令牌缓存与错误处理；使用模拟 HTTP 传输，不访问真实飞书。"""

import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.integrations.feishu import FeishuClient


@pytest.fixture
def settings(env):
    return load_settings({**env, "FEISHU_APP_ID": "cli_test123", "FEISHU_APP_SECRET": "secret-value"})


def client_with(handler, settings):
    calls = []

    def record(request):
        calls.append(request)
        return handler(request)

    return FeishuClient(settings, httpx.Client(transport=httpx.MockTransport(record))), calls


def test_authorize_url_uses_registered_redirect(settings):
    client, _ = client_with(lambda request: httpx.Response(500), settings)
    url = urlsplit(client.authorize_url("state-1"))
    assert (
        f"{url.scheme}://{url.netloc}{url.path}" == "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
    )
    assert parse_qs(url.query) == {
        "client_id": ["cli_test123"],
        "response_type": ["code"],
        "redirect_uri": ["http://localhost:3000/api/session/feishu/callback"],
        "state": ["state-1"],
    }


def test_code_exchange_and_user_info(settings):
    def handler(request):
        if request.url.path.endswith("/authen/v2/oauth/token"):
            body = json.loads(request.content)
            assert body == {
                "grant_type": "authorization_code",
                "client_id": "cli_test123",
                "client_secret": "secret-value",
                "code": "abc",
                "redirect_uri": "http://localhost:3000/api/session/feishu/callback",
            }
            return httpx.Response(200, json={"code": 0, "access_token": "u-token", "expires_in": 7200})
        assert request.url.path.endswith("/authen/v1/user_info")
        assert request.headers["authorization"] == "Bearer u-token"
        return httpx.Response(200, json={"code": 0, "data": {"user_id": "u1", "tenant_key": "t"}})

    client, _ = client_with(handler, settings)
    assert client.user_info(client.exchange_code("abc"))["user_id"] == "u1"


def test_paged_members_and_cached_tenant_token(settings):
    pages = {
        None: {"has_more": True, "page_token": "p2", "items": [{"user_id": "a"}]},
        "p2": {"has_more": False, "items": [{"user_id": "b"}]},
    }

    def handler(request):
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t-token", "expire": 7200})
        assert request.headers["authorization"] == "Bearer t-token"
        query = parse_qs(request.url.query.decode())
        assert query["user_id_type"] == ["user_id"] and query["page_size"] == ["50"]
        return httpx.Response(200, json={"code": 0, "data": pages[query.get("page_token", [None])[0]]})

    client, calls = client_with(handler, settings)
    assert [item["user_id"] for item in client.department_users("od-1")] == ["a", "b"]
    assert [item["user_id"] for item in client.department_users("od-1")] == ["a", "b"]
    assert sum(call.url.path.endswith("tenant_access_token/internal") for call in calls) == 1


def test_errors_do_not_echo_upstream_message(settings):
    def handler(request):
        return httpx.Response(400, json={"code": 99991672, "msg": "secret detail app_secret=xyz"})

    client, _ = client_with(handler, settings)
    with pytest.raises(ApiError) as error:
        client.scope_department_ids()
    assert "通讯录权限" in error.value.message and "xyz" not in error.value.message


def test_unconfigured_client_refuses(env):
    client = FeishuClient(
        load_settings(env), httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    )
    assert not client.configured
    with pytest.raises(ApiError) as error:
        client.authorize_url("s")
    assert error.value.status == 503
