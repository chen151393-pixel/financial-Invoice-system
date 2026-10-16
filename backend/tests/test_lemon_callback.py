"""回调探测与授权上下文测试：不发起柠檬云网络调用、不将收到 code 当作绑定成功。"""

from urllib.parse import parse_qs, urlsplit

import pytest
from backend.app import create_app
from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.modules.sync.dto import LemonAuthorizationRequest
from backend.modules.sync.lemon_service import (
    CALLBACK_COOKIE,
    CALLBACK_PATH,
    LemonCallbackService,
)
from fastapi.testclient import TestClient

PREFIX = "/api/lemon/oauth"


@pytest.fixture
def lemon_api(context):
    context.settings.origin = "https://invoice.example.invalid"
    context.settings.lemon_app_id = "10294"
    app = create_app(context.settings, context.ns, context.engine)
    with TestClient(app, base_url=context.settings.origin) as client:
        login = client.post(
            "/api/session",
            headers={"Origin": context.settings.origin},
            json={"username": "admin", "password": context.settings.admin_password},
        )
        assert login.status_code == 200
        yield client, context


def begin(client, context, mobile="19000000001"):
    return client.post(
        PREFIX + "/authorize",
        headers={"Origin": context.settings.origin},
        json={"mobile": mobile},
    )


def test_public_probe_works_without_credentials_or_session(lemon_api):
    client, context = lemon_api
    context.settings.lemon_app_id = ""
    client.cookies.clear()
    response = client.get(CALLBACK_PATH, headers={"Host": "evil.invalid"})
    assert response.status_code == 200
    assert response.json()["callbackUrl"] == context.settings.origin + CALLBACK_PATH
    assert response.json()["callbackReady"] is True
    assert response.json()["callbackReceived"] is False
    assert response.json()["accountBound"] is False
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "set-cookie" not in response.headers


def test_authorize_uses_official_parameters_and_separate_cookie(lemon_api):
    client, context = lemon_api
    response = begin(client, context)
    assert response.status_code == 200
    url = urlsplit(response.json()["authorizationUrl"])
    assert url.scheme == "https" and url.netloc == "open2.ningmengyun.com"
    assert url.path == "/OAuthPage/OAPage/Index"
    assert parse_qs(url.query) == {
        "appId": ["10294"],
        "mobile": ["19000000001"],
        "redirect_uri": [context.settings.origin + CALLBACK_PATH],
    }
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert f"Path={CALLBACK_PATH}" in cookie and "Max-Age=600" in cookie
    assert "ns_session" not in cookie
    assert response.json()["bindingReady"] is False
    assert "password" not in response.text and "secret" not in response.text.lower()


def test_callback_uses_context_without_strict_session_cookie_and_no_secrets(lemon_api, caplog):
    client, context = lemon_api
    begin(client, context)
    token = client.cookies.get(CALLBACK_COOKIE)
    client.cookies.clear()
    response = client.get(
        CALLBACK_PATH,
        params={"code": "sensitive-code-never-return"},
        headers={"Cookie": f"{CALLBACK_COOKIE}={token}"},
    )
    assert response.status_code == 200
    assert response.json()["callbackReceived"] is True
    assert response.json()["accountBound"] is False
    assert response.json()["bindingReady"] is False
    assert "sensitive-code-never-return" not in response.text
    assert token not in response.text
    assert "sensitive-code-never-return" not in caplog.text
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert response.headers["referrer-policy"] == "no-referrer"
    replay = client.get(
        CALLBACK_PATH,
        params={"code": "sensitive-code-never-return"},
        headers={"Cookie": f"{CALLBACK_COOKIE}={token}"},
    )
    assert replay.status_code == 400
    assert context.ns.writes == []


def test_callback_from_other_browser_is_rejected(lemon_api):
    client, context = lemon_api
    begin(client, context)
    original = client.cookies.get(CALLBACK_COOKIE)
    client.cookies.clear()
    assert client.get(CALLBACK_PATH, params={"code": "code"}).status_code == 400
    # 未携带上下文的请求不能消耗另一个浏览器的授权。
    assert (
        client.get(
            CALLBACK_PATH,
            params={"code": "code"},
            headers={"Cookie": f"{CALLBACK_COOKIE}={original}"},
        ).status_code
        == 200
    )


def test_logout_invalidates_callback(lemon_api):
    client, context = lemon_api
    begin(client, context)
    assert client.delete("/api/session", headers={"Origin": context.settings.origin}).status_code == 200
    assert client.get(CALLBACK_PATH, params={"code": "code"}).status_code == 401


def test_new_authorization_invalidates_previous_context(lemon_api):
    client, context = lemon_api
    begin(client, context)
    old = client.cookies.get(CALLBACK_COOKIE)
    begin(client, context, "19000000002")
    current = client.cookies.get(CALLBACK_COOKIE)
    assert old != current
    assert (
        client.get(
            CALLBACK_PATH,
            params={"code": "code"},
            headers={"Cookie": f"{CALLBACK_COOKIE}={old}"},
        ).status_code
        == 400
    )
    assert (
        client.get(
            CALLBACK_PATH,
            params={"code": "code"},
            headers={"Cookie": f"{CALLBACK_COOKIE}={current}"},
        ).status_code
        == 200
    )


def test_expired_and_restarted_contexts_are_rejected(context):
    now = [100.0]
    service = LemonCallbackService(context.settings, lambda **_kwargs: "user:admin", clock=lambda: now[0])
    context.settings.lemon_app_id = "10294"
    body = LemonAuthorizationRequest(mobile="19000000001")
    _, token = service.begin("user:admin", "browser-session", body)
    from backend.modules.sync.dto import LemonCallbackRequest

    callback = LemonCallbackRequest(code="code")
    now[0] += 600
    with pytest.raises(ApiError, match="已过期"):
        service.receive(callback, token)
    restarted = LemonCallbackService(context.settings, lambda **_kwargs: "user:admin")
    with pytest.raises(ApiError, match="缺失"):
        restarted.receive(callback, token)


@pytest.mark.parametrize(
    "query",
    [
        "code=",
        "code=one&code=two",
        "code=%0Aprivate",
        "code=a+b",
        "code=code&redirect_uri=https://evil.invalid",
        "code=" + "x" * 2049,
    ],
)
def test_invalid_query_is_sanitized_and_does_not_consume_context(lemon_api, query):
    client, context = lemon_api
    begin(client, context)
    response = client.get(CALLBACK_PATH + "?" + query)
    assert response.status_code == 400
    assert "private" not in response.text
    assert client.get(CALLBACK_PATH, params={"code": "valid-code"}).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"mobile": 19000000001},
        {"mobile": "bad"},
        {"mobile": "19000000001", "role": "admin"},
        {"mobile": "19000000001", "redirect_uri": "https://evil.invalid"},
        {},
    ],
)
def test_authorization_input_is_validated(lemon_api, body):
    client, context = lemon_api
    response = client.post(PREFIX + "/authorize", headers={"Origin": context.settings.origin}, json=body)
    assert response.status_code == 400
    assert "set-cookie" not in response.headers


def test_authentication_origin_and_service_role(lemon_api):
    client, context = lemon_api
    assert (
        client.post(
            PREFIX + "/authorize", headers={"Origin": "https://evil.invalid"}, json={"mobile": "19000000001"}
        ).status_code
        == 403
    )
    client.cookies.clear()
    assert begin(client, context).status_code == 401
    assert client.get(PREFIX + "/configuration").status_code == 401
    response = client.post(
        PREFIX + "/authorize",
        headers={"Authorization": f"Bearer {context.settings.service_key}"},
        json={"mobile": "19000000001"},
    )
    assert response.status_code == 403


def test_configuration_reports_readiness_separately(lemon_api):
    client, context = lemon_api
    context.settings.lemon_app_id = ""
    result = client.get(PREFIX + "/configuration").json()
    assert result["callbackReady"] is True
    assert result["bindingReady"] is False
    assert result["authorization"]["allowed"] is False
    assert begin(client, context).status_code == 503


@pytest.mark.parametrize("value", ["0", "-1", "abc", "2147483648", "1.0"])
def test_invalid_app_id_rejected_at_startup(value):
    with pytest.raises(ValueError, match="LEMON_OPEN2_APP_KEY"):
        load_settings({"LEMON_OPEN2_APP_KEY": value})


def test_app_id_can_be_missing_until_customer_service_opens_application():
    assert load_settings({}).lemon_app_id == ""
    assert load_settings({"LEMON_OPEN2_APP_KEY": "10294"}).lemon_app_id == "10294"
