"""同步历史使用隔离数据库验证合并分页、身份范围、失败详情及遗留执行状态。"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.sync.dao import ns_run_dao, sync_run_dao
from backend.tests.sync.test_ns_plan import ADMIN, Pulls, page, services
from backend.tests.sync.test_ns_runs import RANGE, body
from backend.tests.sync.test_ns_runs import engine as engine
from backend.tests.test_lemon_binding import login
from fastapi.testclient import TestClient

NOW = datetime(2026, 10, 30, 8)


def scheduled(engine, world, request_id, at=NOW):
    with engine.begin() as connection:
        return sync_run_dao.create(
            connection,
            {
                "scope_key": world.scope,
                "request_id": request_id,
                "source": "ns_customs",
                "trigger_type": "schedule",
                "started_by": ADMIN,
                "started_at": at,
                "phase": "completed",
                "fetched_count": 2,
                "created_count": 2,
                "updated_count": 0,
                "failed_count": 0,
                "configuration": {"kind": "customs-declarations", **RANGE},
            },
        )


def manual(engine, world, *, owner=ADMIN, status="completed", at=NOW, run_id=None):
    request = body(requestId=str(uuid4()), offset=20)
    with engine.begin() as connection:
        ns_run_dao.create(
            connection,
            {
                "scope_key": world.ns_runs.scope(owner),
                "request_id": request.requestId,
                "kind": request.kind,
                "request": request.snapshot(),
                "status": status,
                "created_at": at,
                "updated_at": at,
                "run_id": run_id,
                "result": page(status, failed=1 if status == "partial" else 0),
            },
        )
    return request.requestId


def test_history_merges_and_paginates_without_counting_scheduled_pages(engine):
    world = services(engine, Pulls())
    manual_id = manual(engine, world)
    plan_id = str(uuid4())
    run_id = scheduled(engine, world, plan_id, NOW - timedelta(minutes=1))
    manual(engine, world, run_id=run_id)  # 定时分页不能再次计为手动执行
    manual(engine, world, owner="other-admin")
    other_account = services(engine, Pulls(account="other-account"))
    manual(engine, other_account)
    scheduled(engine, other_account, str(uuid4()))
    first = world.batches.list(ADMIN, size=1)
    second = world.batches.list(ADMIN, page=2, size=1)
    assert first["total"] == 2 and first["pages"] == 2
    assert first["counts"] == {"completed": 2}
    assert first["items"][0]["requestId"] == manual_id
    assert first["items"][0]["recordType"] == "manual"
    assert second["items"][0]["requestId"] == plan_id
    assert second["items"][0]["recordType"] == "plan"


def test_manual_detail_preserves_failures_counts_and_request_range(engine):
    world = services(engine, Pulls())
    request_id = manual(engine, world, status="partial")
    detail = world.batches.read(ADMIN, request_id, "manual")
    assert detail["phase"] == "partial" and not detail["poll"]
    assert detail["startDate"] == RANGE["startDate"]
    assert (detail["fetched"], detail["created"], detail["failed"]) == (2, 2, 1)
    assert detail["pages"][0]["index"] == 2
    assert detail["pages"][0]["failures"][0] == {
        "id": "9",
        "number": "CD9",
        "status": "failed",
        "reason": "缺少字段",
    }
    assert world.batches.list(ADMIN, phase="partial")["total"] == 1
    assert world.batches.list(ADMIN, phase="completed")["total"] == 0


def test_manual_history_uses_effective_running_state_for_filter_and_counts(engine):
    world = services(engine, Pulls())
    orphan = manual(engine, world, status="running")
    active = manual(engine, world, status="running")
    interrupted = manual(engine, world, status="interrupted")
    scope = world.ns_runs.scope(ADMIN)
    world.ns_runs.active[scope, active] = world.ns_runs.pulls.progress.create(ADMIN)["progressId"]
    result = world.batches.list(ADMIN, phase="unknown")
    assert result["counts"] == {"unknown": 2, "running": 1}
    assert {r["requestId"] for r in result["items"]} == {orphan, interrupted}
    detail = world.batches.read(ADMIN, orphan, "manual")
    assert detail["phase"] == "unknown" and not detail["poll"]
    assert detail["finishedAt"] is None
    assert detail["pages"][0]["error"]
    assert world.batches.read(ADMIN, active, "manual")["poll"]


def test_record_type_disambiguates_same_uuid_and_preserves_access_boundaries(engine):
    world = services(engine, Pulls(), admins={ADMIN, "other-admin"})
    request_id = manual(engine, world)
    scheduled(engine, world, request_id)
    assert world.batches.read(ADMIN, request_id)["recordType"] == "plan"
    assert world.batches.read(ADMIN, request_id, "manual")["recordType"] == "manual"
    for owner, record_type, expected in [("viewer", "manual", 403), ("other-admin", "manual", 404)]:
        with pytest.raises(ApiError) as caught:
            world.batches.read(owner, request_id, record_type)
        assert caught.value.status == expected
    with pytest.raises(ApiError) as caught:
        world.batches.list("viewer")
    assert caught.value.status == 403


def test_failed_restlet_request_is_visible_without_inventing_saved_counts(engine):
    world = services(engine, Pulls(ApiError(502, "NS 同规则查询失败（HTTP 404）")))
    request = body(requestId=str(uuid4()))
    world.ns_runs.start(ADMIN, request)
    result = world.batches.list(ADMIN, phase="failed")
    assert result["total"] == 1
    row = result["items"][0]
    assert "HTTP 404" in row["message"]
    assert (row["fetched"], row["created"], row["updated"]) == (0, 0, 0)
    assert "HTTP 404" in world.batches.read(ADMIN, request.requestId, "manual")["pages"][0]["error"]


def test_history_http_routes_keep_record_type_and_authentication(context, monkeypatch):
    app = create_app(context.settings, context.ns, context.engine)
    monkeypatch.setattr(app.state.ns_plan_worker, "start", lambda: None)
    world = services(context.engine, Pulls(account=context.settings.account))
    request_id = manual(context.engine, world, status="partial")
    scheduled(context.engine, world, request_id)
    with TestClient(app) as client:
        client.headers["Origin"] = context.settings.origin
        path = f"/api/sync/ns/batches/{request_id}"
        assert client.get(path + "?recordType=manual").status_code == 401
        login(client, context.settings)
        listing = client.get("/api/sync/ns/batches?phase=partial&pageSize=1")
        assert listing.status_code == 200
        assert listing.json()["total"] == 1 and listing.json()["counts"] == {"completed": 1, "partial": 1}
        manual_result = client.get(path + "?recordType=manual")
        assert manual_result.status_code == 200 and manual_result.json()["recordType"] == "manual"
        assert manual_result.json()["pages"][0]["failures"][0]["number"] == "CD9"
        assert client.get(path).json()["recordType"] == "plan"
        assert client.get(path + "?recordType=invalid").status_code == 400
        assert client.get("/api/sync/ns/batches?phase=invalid").status_code == 400
        client.cookies.clear()
        client.headers["Authorization"] = "Bearer " + context.settings.service_key
        assert client.get(path + "?recordType=manual").status_code in (401, 403)
