import pytest
from backend.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client(context):
    with TestClient(create_app(context.settings, context.ns, context.engine)) as api:
        yield api


def login(client, context):
    response = client.post(
        "/api/session",
        headers={"Origin": context.settings.origin},
        json={"username": "admin", "password": context.settings.admin_password},
    )
    assert response.status_code == 200
    return response


@pytest.mark.parametrize("password", ["a", "短密码", "p" * 15])
def test_short_password_requires_matching_credentials(client, context, password):
    context.settings.admin_password = password
    headers = {"Origin": context.settings.origin}
    for username, supplied_password in [("admin", "wrong"), ("other", password)]:
        response = client.post(
            "/api/session",
            headers=headers,
            json={"username": username, "password": supplied_password},
        )
        assert response.status_code == 401
        assert "set-cookie" not in response.headers
    assert client.get("/api/ns/status").status_code == 401

    response = login(client, context)
    assert response.json() == {"authenticated": True}
    assert client.get("/api/ns/status").status_code == 200


@pytest.mark.parametrize("password", ["", "provided-password"])
def test_unconfigured_password_does_not_allow_login(client, context, password):
    context.settings.admin_password = ""
    response = client.post(
        "/api/session",
        headers={"Origin": context.settings.origin},
        json={"username": "admin", "password": password},
    )
    assert response.status_code == 503
    assert "set-cookie" not in response.headers
    assert client.get("/api/ns/status").status_code == 401


def test_one_domain_static_auth_csrf_and_token_not_exposed(client, context):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/ns/status").status_code == 401
    assert "NetSuite 发票对账平台" in client.get("/").text
    assert client.get("/.env").status_code == 404
    assert client.get("/api/missing").status_code == 404
    response = login(client, context)
    assert (
        "HttpOnly" in response.headers["set-cookie"] and "SameSite=strict" in response.headers["set-cookie"]
    )
    assert "private_key" not in client.get("/api/ns/status").text
    response = client.post("/api/ns/connect", headers={"Origin": "https://evil.invalid"}, json={})
    assert response.status_code == 403
    response = client.post("/api/ns/connect", headers={"Origin": context.settings.origin}, json={})
    assert response.status_code == 200 and "test-token" not in response.text
    assert client.get("/api/openapi.json").status_code == 200


def test_logout_ends_session(client, context):
    login(client, context)
    headers = {"Origin": context.settings.origin}
    assert client.get("/api/ns/status").status_code == 200
    assert client.delete("/api/session", headers=headers).status_code == 200
    assert client.get("/api/ns/status").status_code == 401


def test_service_key_is_separate(client, context):
    login(client, context)
    client.cookies.clear()
    assert client.get("/api/ns/status", headers={"Authorization": "Bearer ns-m2m-token"}).status_code == 401
    headers = {"Authorization": f"Bearer {context.settings.service_key}"}
    assert client.get("/api/ns/status", headers=headers).status_code == 200


def test_size_content_type_invalid_json_and_login_throttle(client, context):
    assert client.post("/api/session", content="{}").status_code == 415
    assert (
        client.post(
            "/api/session", content='{"number":NaN}', headers={"Content-Type": "application/json"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/session",
            content='"' + "a" * (129 * 1024) + '"',
            headers={"Content-Type": "application/json"},
        ).status_code
        == 413
    )
    for _ in range(10):
        assert (
            client.post(
                "/api/session",
                headers={"Origin": context.settings.origin},
                json={"username": "admin", "password": "wrong"},
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/session",
            headers={"Origin": context.settings.origin},
            json={"username": "admin", "password": context.settings.admin_password},
        ).status_code
        == 429
    )


def test_https_cookie_and_failure_do_not_expose_secrets(context):
    context.settings.origin = "https://invoice.example.com"
    with TestClient(
        create_app(context.settings, context.ns, context.engine), base_url=context.settings.origin
    ) as client:
        response = login(client, context)
        assert "Secure" in response.headers["set-cookie"]
        assert "strict-transport-security" in response.headers

        def fail():
            raise RuntimeError("secret-password-and-token")

        context.ns.token = fail
        response = client.post("/api/ns/connect", json={}, headers={"Origin": context.settings.origin})
        assert response.status_code == 500 and "secret-password" not in response.text
