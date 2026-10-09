"""免登录页面只向本机同源浏览器签发会话；后端授权边界保持不变。"""

import pytest
from backend.app import create_app
from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.modules.identity.service import IdentityService
from fastapi.testclient import TestClient


def test_local_session_keeps_admin_owner_and_protected_endpoints(context):
    context.settings.local_browser_access = True
    context.settings.admin_password = ""
    app = create_app(context.settings, context.ns, context.engine)
    with TestClient(app, base_url=context.settings.origin, client=("127.0.0.1", 12345)) as client:
        assert client.get("/api/ns/status").status_code == 401
        response = client.post("/api/session/local", json={}, headers={"Origin": context.settings.origin})
        assert response.status_code == 200
        assert response.json() == {"authenticated": True}
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        first_token = client.cookies.get("ns_session")
        assert app.state.identity.owner(session_token=first_token) == "user:admin"
        assert client.get("/api/ns/status").status_code == 200
        response = client.post("/api/session/local", json={}, headers={"Origin": context.settings.origin})
        assert response.status_code == 200
        assert client.cookies.get("ns_session") != first_token
        with pytest.raises(ApiError):
            app.state.identity.owner(session_token=first_token)
        assert (
            client.post("/api/ns/connect", json={}, headers={"Origin": "https://evil.invalid"}).status_code
            == 403
        )
        assert not context.ns.writes


@pytest.mark.parametrize(
    "enabled,ip,origin,host",
    [
        (False, "127.0.0.1", "http://localhost:3000", "localhost:3000"),
        (True, "192.168.1.8", "http://localhost:3000", "localhost:3000"),
        (True, "127.0.0.1", "https://evil.invalid", "localhost:3000"),
        (True, "127.0.0.1", None, "localhost:3000"),
        (True, "127.0.0.1", "http://localhost:3000", "evil.invalid"),
        (True, "unknown", "http://localhost:3000", "localhost:3000"),
    ],
)
def test_local_entry_rejects_remote_cross_site_or_disabled(context, enabled, ip, origin, host):
    context.settings.local_browser_access = enabled
    app = create_app(context.settings, context.ns, context.engine)
    headers = {"Host": host, "X-Forwarded-For": "127.0.0.1"}
    if origin is not None:
        headers["Origin"] = origin
    with TestClient(app, base_url=context.settings.origin, client=(ip, 12345)) as client:
        response = client.post("/api/session/local", json={}, headers=headers)
        assert response.status_code == 403
        assert "set-cookie" not in response.headers
        assert client.get("/api/ns/status").status_code == 401


@pytest.mark.parametrize(
    "extra",
    [
        {"HOST": "0.0.0.0"},
        {"APP_ORIGIN": "https://business.example.com"},
        {"LOCAL_BROWSER_ACCESS": "yes"},
    ],
)
def test_local_entry_config_rejects_public_deployment(env, extra):
    with pytest.raises(ValueError):
        load_settings({**env, "LOCAL_BROWSER_ACCESS": "true", **extra})


def test_local_entry_preserves_service_identity_and_ipv6(env):
    settings = load_settings(
        {**env, "LOCAL_BROWSER_ACCESS": "true", "APP_ORIGIN": "http://[::1]:3000", "HOST": "::1"}
    )
    identity = IdentityService(settings)
    token = identity.open_local_session(origin=settings.origin, host="[::1]:3000", ip="::1")
    assert identity.owner(session_token=token) == "user:admin"
    assert identity.owner(authorization="Bearer " + settings.service_key) == "service:feishu"
