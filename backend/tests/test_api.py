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


def test_full_http_contract_preview_execute_history_and_logout(client, context):
    login(client, context)
    headers = {"Origin": context.settings.origin}
    p = client.post(
        "/api/ns/preview",
        headers=headers,
        json={"operation": "update", "type": "vendorBill", "id": "1", "payload": {"memo": "checked"}},
    )
    assert p.status_code == 201
    preview_id = p.json()["id"]
    for body in [
        {"previewId": preview_id, "confirm": "true"},
        {"previewId": preview_id, "confirm": True, "payload": {"memo": "tampered"}},
    ]:
        assert client.post("/api/ns/execute", headers=headers, json=body).status_code == 400
    result = client.post("/api/ns/execute", headers=headers, json={"previewId": preview_id, "confirm": True})
    assert result.json()["state"] == "succeeded"
    assert client.get(f"/api/ns/jobs/{preview_id}").json()["state"] == "succeeded"
    assert client.get("/api/ns/jobs").json()[0]["id"] == preview_id
    assert client.delete("/api/session", headers=headers).status_code == 200
    assert client.get("/api/ns/status").status_code == 401


def test_service_key_is_separate_and_owner_isolation(client, context):
    login(client, context)
    p = client.post(
        "/api/ns/preview",
        headers={"Origin": context.settings.origin},
        json={"operation": "update", "type": "vendorBill", "id": "1", "payload": {"memo": "checked"}},
    ).json()
    client.cookies.clear()
    assert client.get("/api/ns/status", headers={"Authorization": "Bearer ns-m2m-token"}).status_code == 401
    headers = {"Authorization": f"Bearer {context.settings.service_key}"}
    assert client.get("/api/ns/status", headers=headers).status_code == 200
    assert client.get(f"/api/ns/jobs/{p['id']}", headers=headers).status_code == 404


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


def test_text_preview_is_validated_on_server_and_execute_is_still_guarded(client, context):
    login(client, context)
    headers = {"Origin": context.settings.origin}
    body = {"operation": "update", "type": "vendorBill", "id": "1", "payloadText": ""}
    for invalid in ["{", "[]", '{"memo":NaN}', '{"subsidiary":"not-allowed"}']:
        response = client.post("/api/ns/preview-text", json={**body, "payloadText": invalid}, headers=headers)
        assert response.status_code == 400
    assert client.get("/api/ns/jobs").json() == []
    response = client.post(
        "/api/ns/preview-text", json={**body, "payloadText": '{"memo":"校对"}'}, headers=headers
    )
    assert response.status_code == 201
    view = response.json()
    assert view["actions"]["execute"]["allowed"] and view["stateLabel"] == "待确认"
    # 页面许可不是执行许可；配置在提交前改变时，后端必须重新拒绝。
    context.settings.write_enabled = False
    assert not client.get(f"/api/ns/jobs/{view['id']}/view").json()["actions"]["execute"]["allowed"]
    result = client.post("/api/ns/execute", json={"previewId": view["id"], "confirm": True}, headers=headers)
    assert result.status_code == 403 and not context.ns.writes


def test_record_query_rejects_empty_detail_on_server(client, context):
    login(client, context)
    headers = {"Origin": context.settings.origin}
    body = {"type": "vendorBill", "id": "", "mode": "detail"}
    assert client.post("/api/ns/query", json=body, headers=headers).status_code == 400
    assert client.post("/api/ns/query", json={**body, "mode": "list"}, headers=headers).status_code == 200
