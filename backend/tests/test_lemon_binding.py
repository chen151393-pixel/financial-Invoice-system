"""已有账号绑定：真实 HTTP 边界与假上游，禁止调用生产柠檬云。"""

from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.integrations.lemon.existing_account import LemonExistingAccount
from backend.modules.sync.service.lemon_binding_service import LemonBindingService
from fastapi.testclient import TestClient

BASE = "/api/sync/lemon/binding"
MOBILE = "13800000001"


class FakeLemon:
    def __init__(self):
        self.bound = False
        self.calls = []
        self.failure = None
        self.token_failure = False

    def authorization_url(self, mobile):
        return "https://open2.ningmengyun.com/OAuthPage/OAPage/Index?mobile=" + mobile

    def app_token(self):
        if self.token_failure:
            raise ApiError(502, "应用授权失败")
        return "private-app-token"

    def bind(self, token, mobile, code, password):
        self.calls.append((mobile, code))
        assert token == "private-app-token" and password == "secret-password"
        if self.failure:
            raise self.failure
        self.bound = True

    def verify(self, mobile):
        assert mobile == MOBILE
        if not self.bound:
            raise ApiError(409, "尚未核实绑定")


@pytest.fixture
def binding(context):
    settings = replace(
        context.settings,
        origin="https://invoice.example",
        lemon_app_id="12345",
        lemon_app_secret="app-secret",
        lemon_redirect_uri="https://invoice.example/api/lemon/oauth/callback",
    )
    upstream = FakeLemon()
    app = create_app(settings, context.ns, context.engine, lemon=upstream)
    with TestClient(app, base_url=settings.origin, follow_redirects=False) as client:
        client.headers["Origin"] = settings.origin
        yield client, app, upstream, settings


def login(client, settings):
    assert (
        client.post(
            "/api/session", json={"username": settings.admin_user, "password": settings.admin_password}
        ).status_code
        == 200
    )


def start(client):
    response = client.post(BASE + "/start", json={"mobile": MOBILE})
    assert response.status_code == 200, response.text
    return response


def callback(client):
    return client.get("/api/lemon/oauth/callback?code=private-code")


def test_complete_binding_persists_and_does_not_claim_sync(binding, context):
    client, app, upstream, settings = binding
    login(client, settings)
    initial = client.get(BASE).json()
    assert initial["phase"] == "unbound" and initial["begin"]["allowed"]
    response = start(client)
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    response = callback(client)
    assert response.status_code == 303
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["location"] == "/sync/lemon?binding=returned"
    assert upstream.calls == []
    state = client.get(BASE).json()
    assert state["confirm"]["allowed"] and state["confirmationMobile"] == MOBILE
    response = client.post(BASE + "/confirm", json={"password": "secret-password"})
    assert response.status_code == 200
    assert response.json()["phase"] == "bound"
    assert response.json()["sync"]["allowed"] is False
    assert not response.json()["begin"]["allowed"]
    assert len(upstream.calls) == 1
    assert "private-" not in response.text and "secret" not in response.text
    restarted = LemonBindingService(settings, context.engine, upstream)
    assert restarted.status("user:admin")["phase"] == "bound"
    assert client.post(BASE + "/confirm", json={"password": "secret-password"}).status_code == 409


def test_requires_identity_and_same_origin(binding):
    client, _, upstream, settings = binding
    assert client.get(BASE).status_code == 401
    assert client.post(BASE + "/start", json={"mobile": MOBILE}).status_code == 401
    login(client, settings)
    assert client.get("/api/session").status_code == 200
    assert (
        client.post(
            BASE + "/start", json={"mobile": MOBILE}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    client.cookies.clear()
    assert (
        client.post(
            BASE + "/start",
            json={"mobile": MOBILE},
            headers={"Authorization": "Bearer " + settings.service_key},
        ).status_code
        == 403
    )
    assert upstream.calls == []


def test_callback_requires_browser_cookie_and_is_one_time(binding):
    client, app, upstream, settings = binding
    login(client, settings)
    response = callback(client)
    assert response.headers["location"].endswith("invalid")
    start(client)
    cookie = client.cookies.get("lemon_binding")
    client.cookies.delete("ns_session")
    assert callback(client).headers["location"].endswith("returned")
    assert callback(client).headers["location"].endswith("invalid")
    assert client.post(BASE + "/confirm", json={"password": "secret-password"}).status_code == 401
    login(client, settings)
    assert client.get(BASE).json()["phase"] == "awaiting_confirmation"
    with pytest.raises(ApiError, match="管理员"):
        app.state.lemon_binding.confirm("user:someone", cookie, "secret-password")
    assert upstream.calls == []


@pytest.mark.parametrize("code", ["", "x" * 2049])
def test_invalid_callback_never_marks_success(binding, code):
    client, _, upstream, settings = binding
    login(client, settings)
    start(client)
    assert (
        client.get("/api/lemon/oauth/callback", params={"code": code}).headers["location"].endswith("invalid")
    )
    assert not client.get(BASE).json()["confirm"]["allowed"]
    assert upstream.calls == []


def test_expired_and_restarted_attempt_require_new_authorization(binding, context):
    client, app, upstream, settings = binding
    login(client, settings)
    start(client)
    cookie = client.cookies.get("lemon_binding")
    app.state.lemon_binding.pending[cookie]["expires"] = 0
    assert callback(client).headers["location"].endswith("invalid")
    assert client.post(BASE + "/confirm", json={"password": "secret-password"}).status_code == 409
    start(client)
    restarted = LemonBindingService(settings, context.engine, upstream)
    assert not restarted.callback(client.cookies.get("lemon_binding"), "code")
    assert restarted.status("user:admin")["begin"]["allowed"]


def test_unknown_result_blocks_retry_and_can_be_verified(binding, context):
    client, _, upstream, settings = binding
    login(client, settings)
    start(client)
    callback(client)
    upstream.failure = ApiError(502, "连接中断")
    assert client.post(BASE + "/confirm", json={"password": "secret-password"}).status_code == 502
    assert client.get(BASE).json()["phase"] == "unknown"
    assert client.post(BASE + "/start", json={"mobile": MOBILE}).status_code == 409
    restarted = LemonBindingService(settings, context.engine, upstream)
    assert restarted.status("user:admin")["phase"] == "unknown"
    assert client.post(BASE + "/verify", json={}).status_code == 409
    upstream.bound = True
    assert client.post(BASE + "/verify", json={}).json()["phase"] == "bound"
    assert len(upstream.calls) == 1


def test_application_auth_failure_does_not_consume_code(binding):
    client, _, upstream, settings = binding
    login(client, settings)
    start(client)
    callback(client)
    upstream.token_failure = True
    assert client.post(BASE + "/confirm", json={"password": "secret-password"}).status_code == 502
    assert client.get(BASE).json()["confirm"]["allowed"]
    assert upstream.calls == []
    upstream.token_failure = False
    assert client.post(BASE + "/confirm", json={"password": "secret-password"}).status_code == 200


def test_rejection_and_invalid_inputs(binding):
    client, _, upstream, settings = binding
    login(client, settings)
    assert client.post(BASE + "/start", json={"mobile": "bad"}).status_code == 400
    assert client.post(BASE + "/start", json={"mobile": MOBILE, "appId": "attacker"}).status_code == 400
    start(client)
    callback(client)
    assert client.post(BASE + "/confirm", json={"password": ""}).status_code == 400
    upstream.failure = ApiError(400, "明确拒绝")
    assert client.post(BASE + "/confirm", json={"password": "secret-password"}).status_code == 400
    assert client.get(BASE).json()["phase"] == "unbound"
    assert client.post(BASE + "/confirm", json={"password": "secret-password"}).status_code == 409


def test_official_protocol_and_secret_redaction(binding, caplog):
    _, _, _, settings = binding
    requests = []

    def handler(request):
        requests.append(request)
        if "GetAppAccessToken" in request.url.path:
            return httpx.Response(200, json={"State": 1000, "Data": {"access_token": "global"}})
        if "LinkUserToApp" in request.url.path:
            return httpx.Response(200, json={"State": 1000, "Data": True})
        return httpx.Response(200, json={"State": 1000, "Data": {"userId": MOBILE, "Mobile": MOBILE}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = LemonExistingAccount(settings, http)
        query = parse_qs(urlsplit(client.authorization_url(MOBILE)).query)
        assert query == {
            "appId": ["12345"],
            "mobile": [MOBILE],
            "redirect_uri": [settings.lemon_redirect_uri],
        }
        client.bind(client.app_token(), MOBILE, "code-secret", "password-secret")
        import json

        body = json.loads(requests[1].content)
        assert body == {
            "appId": 12345,
            "appSecret": "app-secret",
            "code": "code-secret",
            "mobile": MOBILE,
            "userId": MOBILE,
            "orgId": 0,
            "password": "password-secret",
        }
        assert requests[1].headers["Authorization"] == "Bearer global"
        client.verify(MOBILE)
    assert "password-secret" not in caplog.text and "code-secret" not in caplog.text


@pytest.mark.parametrize("payload", [{"State": 1000, "Data": False}, {}, {"State": 9999, "Msg": "SECRET"}])
def test_upstream_false_and_malformed_responses_are_not_success(binding, payload):
    _, _, _, settings = binding
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as http:
        with pytest.raises(ApiError) as error:
            LemonExistingAccount(settings, http).bind("token", MOBILE, "code", "password")
        assert "SECRET" not in error.value.message


@pytest.mark.parametrize(
    "changes",
    [
        {"lemon_app_secret": ""},
        {"lemon_app_id": "not-an-id"},
        {"lemon_app_id": "9" * 5000},
        {"lemon_host": "https://untrusted.example"},
        {"lemon_redirect_uri": "https://other.example/api/lemon/oauth/callback"},
        {"lemon_redirect_uri": "http://invoice.example/api/lemon/oauth/callback"},
        {"lemon_redirect_uri": "https://invoice.example/api/lemon/oauth/callback?extra=1"},
    ],
)
def test_invalid_configuration_blocks_authorization(binding, context, changes):
    _, _, upstream, settings = binding
    service = LemonBindingService(replace(settings, **changes), context.engine, upstream)
    assert not service.status("user:admin")["begin"]["allowed"]
    with pytest.raises(ApiError) as error:
        service.begin("user:admin", MOBILE)
    assert error.value.status == 503
    assert upstream.calls == []


def test_foreign_pending_context_and_duplicate_callback_are_rejected(binding):
    client, app, upstream, settings = binding
    login(client, settings)
    start(client)
    cookie = client.cookies.get("lemon_binding")
    response = client.get("/api/lemon/oauth/callback?code=first&code=second")
    assert response.headers["location"].endswith("invalid")
    callback(client)
    app.state.lemon_binding.pending[cookie]["owner"] = "user:other"
    with pytest.raises(ApiError, match="不属于"):
        app.state.lemon_binding.confirm("user:admin", cookie, "secret-password")
    assert upstream.calls == []
