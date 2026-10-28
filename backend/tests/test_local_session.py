"""本机兼容入口不能绕过账号密码登录。"""

import pytest
from backend.app import create_app
from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.modules.identity.service.session_service import IdentityService
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "ip,origin,host",
    [
        ("127.0.0.1", "http://localhost:3000", "localhost:3000"),
        ("192.168.1.8", "http://localhost:3000", "localhost:3000"),
        ("127.0.0.1", "https://evil.invalid", "localhost:3000"),
        ("127.0.0.1", None, "localhost:3000"),
        ("127.0.0.1", "http://localhost:3000", "evil.invalid"),
    ],
)
def test_local_entry_never_issues_passwordless_session(context, ip, origin, host):
    context.settings.admin_password = ""
    app = create_app(context.settings, context.ns, context.engine)
    headers = {"Host": host, "X-Forwarded-For": "127.0.0.1"}
    if origin is not None:
        headers["Origin"] = origin
    with TestClient(app, base_url=context.settings.origin, client=(ip, 12345)) as client:
        response = client.post("/api/session/local", json={}, headers=headers)
        assert response.status_code == 403
        assert "set-cookie" not in response.headers
        assert client.get("/api/session").status_code == 401
        assert client.get("/api/ns/status").status_code == 401
        assert not app.state.identity.sessions
        assert not context.ns.writes


@pytest.mark.parametrize("legacy_value", ["false", "true", "yes"])
def test_retired_switch_cannot_restore_passwordless_sessions(env, legacy_value):
    settings = load_settings({**env, "LOCAL_BROWSER_ACCESS": legacy_value})
    identity = IdentityService(settings)
    with pytest.raises(ApiError) as error:
        identity.open_local_session(origin=settings.origin, host="localhost:3000", ip="127.0.0.1")
    assert error.value.status == 403
    assert not identity.sessions


def test_ipv6_also_requires_password_and_preserves_service_identity(env):
    settings = load_settings({**env, "APP_ORIGIN": "http://[::1]:3000", "HOST": "::1"})
    identity = IdentityService(settings)
    with pytest.raises(ApiError):
        identity.open_local_session(origin=settings.origin, host="[::1]:3000", ip="::1")
    token = identity.login(settings.admin_user, settings.admin_password, origin=settings.origin, ip="::1")
    assert identity.owner(session_token=token) == "user:admin"
    assert identity.owner(authorization="Bearer " + settings.service_key) == "service:feishu"
