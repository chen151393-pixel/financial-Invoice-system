"""账号密码、会话轮换、失效及来源校验的针对性验证。"""

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.identity.service.session_service import IdentityService
from fastapi.testclient import TestClient


def test_custom_account_login_rotation_logout_and_replay(context):
    context.settings.admin_user = "财务管理员"
    app = create_app(context.settings, context.ns, context.engine)
    with TestClient(app, base_url=context.settings.origin) as client:
        headers = {"Origin": context.settings.origin}
        body = {"username": context.settings.admin_user, "password": context.settings.admin_password}
        assert client.get("/api/session").status_code == 401
        assert client.post("/api/session", json=body, headers=headers).status_code == 200
        first = client.cookies.get("ns_session")
        assert app.state.identity.owner(session_token=first) == "user:财务管理员"
        assert client.post("/api/session", json=body, headers=headers).status_code == 200
        second = client.cookies.get("ns_session")
        assert first != second
        with pytest.raises(ApiError):
            app.state.identity.owner(session_token=first)
        assert client.delete("/api/session", headers=headers).status_code == 200
        assert not client.cookies.get("ns_session")
        assert client.get("/api/session").status_code == 401
        assert client.get("/api/session", headers={"Cookie": f"ns_session={second}"}).status_code == 401
        assert not context.ns.writes


def test_expired_session_and_throttle_window(context, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("backend.modules.identity.service.session_service.time.monotonic", lambda: clock[0])
    identity = IdentityService(context.settings)
    args = {"origin": context.settings.origin, "ip": "127.0.0.1"}
    for _ in range(10):
        with pytest.raises(ApiError) as error:
            identity.login("admin", "wrong", **args)
        assert error.value.status == 401
    with pytest.raises(ApiError) as error:
        identity.login("admin", context.settings.admin_password, **args)
    assert error.value.status == 429
    clock[0] += 901
    token = identity.login("admin", context.settings.admin_password, **args)
    assert identity.owner(session_token=token) == "user:admin"
    clock[0] += 8 * 3600
    with pytest.raises(ApiError) as error:
        identity.owner(session_token=token)
    assert error.value.status == 401


@pytest.mark.parametrize("origin", [None, "https://evil.invalid"])
def test_login_and_logout_reject_wrong_origin(context, origin):
    app = create_app(context.settings, context.ns, context.engine)
    body = {"username": "admin", "password": context.settings.admin_password}
    headers = {} if origin is None else {"Origin": origin}
    with TestClient(app, base_url=context.settings.origin) as client:
        assert client.post("/api/session", json=body, headers=headers).status_code == 403
        assert not client.cookies.get("ns_session")
        assert (
            client.post("/api/session", json=body, headers={"Origin": context.settings.origin}).status_code
            == 200
        )
        assert client.delete("/api/session", headers=headers).status_code == 403
        assert client.get("/api/session").status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"username": "", "password": "secret"},
        {"username": "admin", "password": ""},
        {"username": "admin", "password": "secret", "role": "admin"},
        {"username": 123, "password": "secret"},
    ],
)
def test_invalid_login_fields_never_issue_cookie(context, body):
    app = create_app(context.settings, context.ns, context.engine)
    with TestClient(app, base_url=context.settings.origin) as client:
        response = client.post("/api/session", json=body, headers={"Origin": context.settings.origin})
        assert response.status_code == 400
        assert "secret" not in response.text
        assert "set-cookie" not in response.headers
