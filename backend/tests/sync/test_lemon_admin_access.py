"""系统管理员角色接入同步：真实权限表和 HTTP 边界，所有上游使用替身。"""

import hashlib
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.sync.dao import lemon_plan_dao, sync_run_dao
from backend.modules.sync.service.lemon_binding_service import LemonBindingService
from backend.tests.identity.test_feishu_login import FakeFeishu, setup_directory
from backend.tests.sync.test_lemon_background import plan, request
from backend.tests.sync.test_lemon_invoices import OWNER, make_services
from backend.tests.test_lemon_binding import login
from fastapi.testclient import TestClient

BASE = "/api/sync/lemon"
READS = (
    "/batches",
    "/background/configuration",
    "/binding",
    "/invoices/configuration",
    "/invoices/accounts",
)
ACTOR = "user:fs:u-li"


@pytest.fixture
def world(context):
    settings = replace(
        context.settings,
        origin="https://invoice.example",
        lemon_app_id="12345",
        lemon_app_secret="secret",
        lemon_redirect_uri="https://invoice.example/api/lemon/oauth/callback",
    )
    accounts, _, upstream, _ = make_services(context.engine, settings)
    app = create_app(
        settings,
        context.ns,
        context.engine,
        feishu=FakeFeishu(),
        lemon=accounts.binding.client,
        lemon_invoices=upstream,
    )
    # 不启动 lifespan，避免自动调度；后台消费由测试明确驱动。
    admin = TestClient(app, base_url=settings.origin, headers={"Origin": settings.origin})
    login(admin, settings)
    setup_directory(admin, settings, roles={"采购部": ["admin"], "财务部": ["finance"]})
    client = TestClient(app, base_url=settings.origin, headers={"Origin": settings.origin})
    client.cookies.set("ns_session", app.state.identity.issue(ACTOR))
    users = {row["name"]: row for row in admin.get("/api/identity/access").json()["users"]}
    yield SimpleNamespace(
        app=app,
        admin=admin,
        client=client,
        settings=settings,
        engine=context.engine,
        upstream=upstream,
        users=users,
    )
    client.close()
    admin.close()


def test_feishu_admin_reads_existing_configuration_and_worker_consumes_batch(world):
    client, app = world.client, world.app
    assert client.get("/api/session").json()["user"]["canManageAccess"]
    for path in READS:
        response = client.get(BASE + path)
        assert response.status_code == 200, response.text
    assert client.get(BASE + "/binding").json()["phase"] == "bound"
    assert client.get(BASE + "/invoices/configuration").json()["selected"]["asid"] == "7"
    assert client.put(BASE + "/plan", json=plan().model_dump()).status_code == 200
    assert world.admin.get(BASE + "/background/configuration").json()["plan"]["enabled"]
    body = request(accountMode="selected", accountIds=["7"])
    assert client.post(BASE + "/batches", json=body.model_dump()).status_code == 202
    worker = app.state.lemon_worker
    for _ in range(5):
        worker.run_once()
        response = client.get(BASE + "/batches/" + body.requestId)
        assert response.status_code == 200, response.text
        if response.json()["phase"] == "completed":
            break
    assert response.json()["phase"] == "completed"
    with world.engine.connect() as connection:
        row = sync_run_dao.get(connection, worker.scope, body.requestId)
        assert row["started_by"] == ACTOR
        assert lemon_plan_dao.get(connection, worker.scope)["owner"] == ACTOR
    assert world.admin.get(BASE + "/batches").json()["total"] == 1
    binding = app.state.lemon_binding
    expected = hashlib.sha256(
        f"{world.settings.lemon_host}|{world.settings.lemon_app_id}|{OWNER}".encode()
    ).hexdigest()
    assert binding._scope(ACTOR) == binding._scope(OWNER) == expected
    other = LemonBindingService(replace(world.settings, lemon_app_id="different"), None, None)
    assert other._scope(OWNER) != expected


def test_non_admin_and_service_identity_are_denied(world):
    for actor in ("user:fs:u-wang", "service:feishu"):
        world.client.cookies.clear()
        if actor.startswith("user:"):
            world.client.cookies.set("ns_session", world.app.state.identity.issue(actor))
        else:
            world.client.headers["Authorization"] = "Bearer " + world.settings.service_key
        for path in READS:
            assert world.client.get(BASE + path).status_code == 403
        assert world.client.post(BASE + "/batches", json=request().model_dump()).status_code == 403
        assert world.client.put(BASE + "/plan", json=plan().model_dump()).status_code == 403
        with pytest.raises(ApiError) as error:
            world.app.state.lemon_binding._scope(actor)
        assert error.value.status == 403


def test_role_revocation_and_disable_take_effect_without_new_login(world):
    user = world.users["李采购"]
    endpoint = f"/api/identity/users/{user['id']}/access"
    assert world.client.get(BASE + "/batches").status_code == 200
    body = request()
    assert world.client.post(BASE + "/batches", json=body.model_dump()).status_code == 202
    assert (
        world.admin.put(
            endpoint, json={"roles": ["viewer"], "customRoles": True, "enabled": True}
        ).status_code
        == 200
    )
    for path in READS:
        assert world.client.get(BASE + path).status_code == 403
    world.app.state.lemon_worker.run_once()
    assert world.admin.get(BASE + "/batches/" + body.requestId).json()["phase"] == "failed"
    assert world.upstream.pulls == 0
    assert (
        world.admin.put(endpoint, json={"roles": ["admin"], "customRoles": True, "enabled": True}).status_code
        == 200
    )
    assert world.client.get(BASE + "/batches").status_code == 200
    assert (
        world.admin.put(
            endpoint, json={"roles": ["admin"], "customRoles": True, "enabled": False}
        ).status_code
        == 200
    )
    assert world.client.get(BASE + "/batches").status_code == 401
    with pytest.raises(ApiError) as error:
        world.app.state.lemon_binding._scope(ACTOR)
    assert error.value.status == 403


def test_binding_confirmation_remains_bound_to_initiating_admin(world):
    binding = world.app.state.lemon_binding
    binding.pending["test-flow"] = {"owner": ACTOR, "expires": time.monotonic() + 60}
    with pytest.raises(ApiError, match="不属于当前身份"):
        binding.confirm(OWNER, "test-flow", "unused")
