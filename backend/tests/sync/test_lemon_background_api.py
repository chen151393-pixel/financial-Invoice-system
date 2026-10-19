"""后台 HTTP 边界：认证、参数校验、入队响应与持久查询。"""

from dataclasses import replace

from backend.app import create_app
from backend.tests.sync.test_lemon_background import plan, request
from backend.tests.sync.test_lemon_background import world as world
from backend.tests.test_lemon_binding import login
from fastapi.testclient import TestClient


def test_background_api_validation_and_scope(world, context, monkeypatch):
    settings = world.accounts.binding.settings
    app = create_app(
        settings,
        context.ns,
        context.engine,
        lemon=world.accounts.binding.client,
        lemon_invoices=world.upstream,
    )
    # 本项只验收提交协议，消费者独立测试；确保响应不依赖上游速度。
    monkeypatch.setattr(app.state.lemon_worker, "start", lambda: None)
    with TestClient(app, base_url=settings.origin) as client:
        client.headers["Origin"] = settings.origin
        assert client.get("/api/sync/lemon/batches").status_code == 401
        login(client, settings)
        body = request().model_dump()
        response = client.post("/api/sync/lemon/batches", json=body)
        assert response.status_code == 202 and response.json()["phase"] == "queued"
        assert world.upstream.pulls == 0
        assert client.post("/api/sync/lemon/batches", json=body).status_code == 202
        assert client.get("/api/sync/lemon/batches").json()["total"] == 1
        assert client.get("/api/sync/lemon/batches/" + body["requestId"]).json()["phase"] == "queued"
        for change in (
            {"businessTypes": []},
            {"accountMode": "selected"},
            {"owner": "other"},
            {"startDate": "2026-20-10"},
            {"endDate": "2020-01-01"},
            {"accountIds": ["7"]},
        ):
            assert client.post("/api/sync/lemon/batches", json={**body, **change}).status_code == 400
        assert client.get("/api/sync/lemon/batches?page=-1").status_code == 400
        saved = client.put("/api/sync/lemon/plan", json=plan().model_dump())
        assert saved.status_code == 200 and saved.json()["plan"]["enabled"]
        for change in (
            {"times": ["25:00"]},
            {"times": ["02:00", "02:00"]},
            {"lookbackDays": 0},
            {"enabled": "yes"},
        ):
            assert (
                client.put("/api/sync/lemon/plan", json={**plan().model_dump(), **change}).status_code == 400
            )
        client.cookies.clear()
        client.headers["Authorization"] = "Bearer " + settings.service_key
        assert client.get("/api/sync/lemon/batches").status_code in (401, 403)


def test_admin_can_pause_when_integration_configuration_breaks(world):
    world.plans.save("user:admin", plan())
    world.accounts.binding.settings = replace(world.accounts.binding.settings, lemon_app_secret="")
    assert not world.plans.configuration("user:admin")["submit"]["allowed"]
    assert world.plans.configuration("user:admin")["pause"]["allowed"]
    result = world.plans.save("user:admin", plan(revision=1, enabled=False))
    assert not result["plan"]["enabled"] and result["plan"]["nextRunAt"] is None
