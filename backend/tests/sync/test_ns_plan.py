"""NS 定时同步计划：计划编辑、到期入队、按游标分页执行、失败排队、待核实停止与自动暂停。

上游与保存使用替身，不连接真实 NS，也不写入 NS。
"""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.source.service.storage_service import StorageService
from backend.modules.sync.dao import ns_plan_dao, ns_run_dao, sync_run_dao
from backend.modules.sync.dto.ns_plan_dto import SaveNsPlan
from backend.modules.sync.policy.ns_plan_policy import PAUSED_ADMIN, PAUSED_UNKNOWN
from backend.modules.sync.service.ns_batch_service import NsBatchService
from backend.modules.sync.service.ns_job_service import NsJobService
from backend.modules.sync.service.ns_plan_service import NsPlanService
from backend.modules.sync.service.ns_plan_worker import NsPlanWorker
from backend.modules.sync.service.ns_run_service import NsRunService
from backend.modules.sync.service.progress_service import ProgressService
from backend.modules.sync.service.sync_health_service import SyncHealthService
from backend.tests.sync.test_ns_runs import Immediate
from backend.tests.test_lemon_binding import login
from backend.tests.test_source_storage import ACCOUNT, rows
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_sync_optimization import batch as batch
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

ADMIN = "user:admin"
# 北京时间 2026-10-29 10:00
NOW = datetime(2026, 10, 29, 2, 0)


def page(status="completed", *, more=False, cursor=None, created=1, updated=0, failed=0):
    counts = {"saved": 2 - failed, "failed": failed, "skipped": 0, "unknown": 0, "not_processed": 0}
    items = [{"id": "9", "number": "CD9", "status": "failed", "reason": "缺少字段"}] if failed else []
    section = {"created": created, "updated": updated, "linesCreated": 0, "linesUpdated": 0}
    return {
        "count": 2,
        "hasMore": more,
        "nextCursor": cursor,
        "storage": {"customs": section, "purchase": dict(section)},
        "batch": {"status": status, "canContinue": True, "counts": counts, "items": items},
    }


class Pulls:
    """按顺序返回每页结果；元素为异常时抛出，模拟账户锁冲突或数据库中断。"""

    def __init__(self, *outcomes, account=ACCOUNT):
        self.settings = SimpleNamespace(account=account)
        self.progress = ProgressService()
        self.outcomes, self.requests, self.blocked = list(outcomes), [], None

    def ensure_storage(self, kind):
        if self.blocked:
            raise ApiError(503, self.blocked)

    def pull_and_save(self, kind, request, owner):
        self.requests.append((kind, request))
        with self.progress.track(request.progressId, owner):
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome


def services(engine, pulls, admins=None):
    admins = {ADMIN} if admins is None else admins

    def require_admin(owner):
        if owner not in admins:
            raise ApiError(403, "需要系统管理员角色才能管理同步配置与任务")

    ns_runs = NsRunService(engine, pulls, Immediate())
    batches = NsBatchService(engine, ns_runs, require_admin)
    plans = NsPlanService(batches)
    jobs = NsJobService(batches, plans)
    return SimpleNamespace(
        ns_runs=ns_runs,
        batches=batches,
        plans=plans,
        jobs=jobs,
        worker=NsPlanWorker(plans, jobs),
        admins=admins,
        scope=batches.scope(),
    )


def plan(**changes):
    values = {"revision": 0, "enabled": True, "kinds": ["customs-declarations"], "times": ["02:00"]}
    return SaveNsPlan(**{**values, "lookbackDays": 7, **changes})


def due(world, engine, at=NOW):
    with engine.begin() as connection:
        ns_plan_dao.change(connection, world.scope, {"next_run_at": at - timedelta(minutes=1)})


def batches(engine, scope):
    with engine.connect() as connection:
        return sync_run_dao.list_page(connection, scope, 1, 50)[0][::-1]


def pages(engine, run_id):
    with engine.connect() as connection:
        return ns_run_dao.batch_pages(connection, run_id)


def drain(world, now=NOW):
    while world.jobs.step(now):
        pass


def test_plan_save_validates_revision_admin_and_configuration(engine):
    world = services(engine, Pulls())
    view = world.plans.configuration(ADMIN)
    assert view["plan"]["revision"] == 0 and not view["plan"]["enabled"]
    assert view["submit"]["allowed"] and [v["value"] for v in view["kindOptions"]] == [
        "customs-declarations",
        "sub-purchase-orders",
    ]
    saved = world.plans.save(ADMIN, plan(kinds=["sub-purchase-orders", "customs-declarations"]))
    assert saved["plan"]["revision"] == 1 and saved["plan"]["enabled"]
    # 执行顺序固定为先报关单、后子采购单；下次执行按北京时间计算并以 UTC 返回。
    assert saved["plan"]["kinds"] == ["customs-declarations", "sub-purchase-orders"]
    assert saved["plan"]["nextRunAt"].endswith("T18:00:00Z")
    with pytest.raises(ApiError) as stale:
        world.plans.save(ADMIN, plan())
    assert stale.value.status == 409
    with pytest.raises(ApiError) as denied:
        world.plans.save("user:viewer", plan(revision=1))
    assert denied.value.status == 403
    paused = world.plans.save(ADMIN, plan(revision=1, enabled=False))
    assert paused["plan"]["nextRunAt"] is None and not paused["pause"]["allowed"]


@pytest.mark.parametrize(
    "changes",
    [
        {"kinds": []},
        {"kinds": ["customs-declarations", "customs-declarations"]},
        {"kinds": ["purchase-orders"]},
        {"times": ["25:00"]},
        {"lookbackDays": 0},
        {"lookbackDays": 367},
    ],
)
def test_plan_input_rejected_by_backend(changes):
    with pytest.raises(ValidationError):
        plan(**changes)


def test_enable_refused_when_storage_not_ready(engine):
    pulls = Pulls()
    pulls.blocked = "独立MySQL业务库尚未配置"
    world = services(engine, pulls)
    assert not world.plans.configuration(ADMIN)["submit"]["allowed"]
    with pytest.raises(ApiError, match="业务库尚未配置") as error:
        world.plans.save(ADMIN, plan())
    assert error.value.status == 409
    # 停用状态的计划仍可保存，便于先配置后启用。
    assert world.plans.save(ADMIN, plan(enabled=False))["plan"]["revision"] == 1


def test_due_plan_enqueues_once_per_kind_with_frozen_window(engine):
    world = services(engine, Pulls())
    world.plans.save(ADMIN, plan(kinds=["customs-declarations", "sub-purchase-orders"]))
    due(world, engine)
    world.plans.tick(NOW)
    world.plans.tick(NOW)  # 下次时间已推进，同一时点不重复入队
    rows_ = batches(engine, world.scope)
    assert [(r["source"], r["trigger_type"], r["phase"]) for r in rows_] == [
        ("ns_customs", "schedule", "queued"),
        ("ns_purchase", "schedule", "queued"),
    ]
    assert rows_[0]["configuration"]["startDate"] == "2026-10-23"
    assert rows_[0]["configuration"]["endDate"] == "2026-10-29"
    assert rows_[0]["ns_plan_id"] and rows_[0]["plan_id"] is None
    with engine.connect() as connection:
        assert ns_plan_dao.get(connection, world.scope)["next_run_at"] == datetime(2026, 10, 29, 18, 0)
    # 已有活动批次时不叠加；到期计划保持到期，结束后合并为一次回扫。
    due(world, engine)
    world.plans.tick(NOW)
    assert len(batches(engine, world.scope)) == 2


def test_pages_follow_cursor_and_upsert_counts_are_summed(engine):
    cursor = {"afterId": "0", "throughId": None, "offset": 20}
    pulls = Pulls(page(more=True, cursor=cursor, created=2), page(created=0, updated=3))
    world = services(engine, pulls)
    world.plans.save(ADMIN, plan())
    due(world, engine)
    world.worker.run_once()  # SQLite 下命名锁为空操作；一轮入队并推进
    drain(world)
    batch = batches(engine, world.scope)[0]
    assert batch["phase"] == "completed" and batch["finished_at"] is not None
    assert (batch["fetched_count"], batch["created_count"], batch["updated_count"]) == (4, 4, 6)
    sent = [request for _, request in pulls.requests]
    assert [r.cursor.model_dump() for r in sent] == [{"afterId": "0", "throughId": None, "offset": 0}, cursor]
    # worker 按真实当前时间入队，窗口以批次冻结的日期为准，不写死日期。
    window = batch["configuration"]["startDate"], batch["configuration"]["endDate"]
    assert all(r.partialSave and (r.startDate, r.endDate) == window for r in sent)
    assert [p["run_id"] for p in pages(engine, batch["id"])] == [batch["id"]] * 2
    detail = world.batches.read(ADMIN, batch["request_id"])
    assert [p["status"] for p in detail["pages"]] == ["completed", "completed"] and not detail["poll"]
    listing = world.batches.list(ADMIN)
    assert listing["items"][0]["kindLabel"] == "报关单" and listing["plan"]["enabled"]


def test_partial_items_keep_running_and_finish_partial(engine):
    world = services(engine, Pulls(page("partial", failed=1)))
    world.plans.save(ADMIN, plan())
    due(world, engine)
    world.plans.tick(NOW)
    drain(world)
    batch = batches(engine, world.scope)[0]
    assert batch["phase"] == "partial" and batch["failed_count"] == 1
    detail = world.batches.read(ADMIN, batch["request_id"])
    assert detail["pages"][0]["failures"] == [
        {"id": "9", "number": "CD9", "status": "failed", "reason": "缺少字段"}
    ]


def test_lock_conflict_page_waits_then_retries_same_cursor(engine):
    busy = ApiError(409, "当前账户已有采购报关保存操作，请完成后再试")
    pulls = Pulls(busy, page())
    world = services(engine, pulls)
    world.plans.save(ADMIN, plan())
    due(world, engine)
    world.plans.tick(NOW)
    assert world.jobs.step(NOW)  # 第一次执行：手动同步占用账户锁，本页未写入
    first = pages(engine, batches(engine, world.scope)[0]["id"])
    assert [p["status"] for p in first] == ["failed"]
    updated = first[0]["updated_at"].replace(tzinfo=None)
    assert not world.jobs.step(updated + timedelta(seconds=30))  # 间隔未到，不重复争锁
    drain(world, updated + timedelta(seconds=61))
    batch = batches(engine, world.scope)[0]
    assert batch["phase"] == "completed"
    assert pulls.requests[0][1].cursor == pulls.requests[1][1].cursor


def test_repeated_failures_stop_batch_after_limit(engine):
    pulls = Pulls(*[ApiError(502, "NS 列表读取失败")] * 5)
    world = services(engine, pulls)
    world.plans.save(ADMIN, plan())
    due(world, engine)
    world.plans.tick(NOW)
    run_id = batches(engine, world.scope)[0]["id"]
    for _ in range(6):
        # 每次都在上一页结束 2 分钟后推进，越过重新排队间隔。
        done = pages(engine, run_id)
        moment = done[-1]["updated_at"].replace(tzinfo=None) if done else NOW
        world.jobs.step(moment + timedelta(minutes=2))
    batch = batches(engine, world.scope)[0]
    assert batch["phase"] == "failed" and "连续 5 次" in batch["message"]
    assert len(pulls.requests) == 5


def test_unknown_page_stops_batch_and_pauses_plan(engine):
    pulls = Pulls(ApiError(503, "数据库连接中断，请先核实已保存单据，不要自动重试"), page())
    world = services(engine, pulls)
    world.plans.save(ADMIN, plan())
    due(world, engine)
    world.plans.tick(NOW)
    drain(world)
    batch = batches(engine, world.scope)[0]
    assert batch["phase"] == "unknown" and batch["finished_at"] is None
    assert len(pulls.requests) == 1  # 待核实不自动重试
    view = world.plans.configuration(ADMIN)["plan"]
    assert not view["enabled"] and view["pausedReason"] == PAUSED_UNKNOWN
    # 管理员核对后重新保存即恢复，原因清除。
    resumed = world.plans.save(ADMIN, plan(revision=view["revision"]))["plan"]
    assert resumed["enabled"] and resumed["pausedReason"] is None


def test_running_page_after_restart_is_unknown_and_not_rerun(engine):
    world = services(engine, Pulls(page()))
    world.plans.save(ADMIN, plan())
    due(world, engine)
    world.plans.tick(NOW)
    batch = batches(engine, world.scope)[0]
    with engine.begin() as connection:
        # 模拟进程在执行中退出：分页记录保持 running，新进程没有执行标记。
        ns_run_dao.create(
            connection,
            {
                "scope_key": world.scope,
                "request_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "kind": "customs-declarations",
                "request": {"offset": 0, "limit": 20},
                "status": "running",
                "run_id": batch["id"],
            },
        )
    restarted = services(engine, Pulls(page()))
    drain(restarted)
    assert batches(engine, world.scope)[0]["phase"] == "unknown"
    assert restarted.ns_runs.pulls.requests == []


def test_owner_without_admin_role_pauses_plan(engine):
    world = services(engine, Pulls(page()))
    world.plans.save(ADMIN, plan())
    world.admins.clear()
    due(world, engine)
    world.plans.tick(NOW)
    assert batches(engine, world.scope) == []
    with engine.connect() as connection:
        saved = ns_plan_dao.get(connection, world.scope)
    assert not saved["enabled"] and saved["configuration"]["pausedReason"] == PAUSED_ADMIN


def test_plan_pages_counted_once_in_sync_health(engine):
    world = services(
        engine, Pulls(page(more=True, cursor={"afterId": "5", "throughId": None, "offset": 0}), page())
    )
    world.plans.save(ADMIN, plan())
    due(world, engine)
    world.plans.tick(NOW)
    drain(world)
    health = SyncHealthService(engine).health(NOW.replace(tzinfo=timezone.utc))
    customs = next(row for row in health.rows if row.key == "ns-customs")
    assert sum(day.runs for day in customs.days) == 1


def test_scheduled_run_updates_existing_documents_and_fills_fields(batch, engine):
    """真实 source 保存：首次新增、计划再次回扫只更新并补齐缺失字段，不新增重复单据。"""
    ns_, records_page, records, _ = batch
    line_type = ns_.settings.pl_lookup["customs_line"]["type"]
    original = {key: deepcopy(value) for key, value in records.items() if key[0] == line_type}
    for key in original:
        records[key].pop("custrecord_swc_huge", None)  # 首次同步时 NS 尚未填写规格型号
    storage = StorageService(ns_, engine)
    rows_ = [
        {"id": row["id"], "number": row["record"]["name"], "record": row["record"]} for row in records_page
    ]

    class StoragePulls(Pulls):
        def pull_and_save(self, kind, request, owner):
            self.requests.append((kind, request))
            with self.progress.track(request.progressId, owner) as report:
                listing = {"rows": rows_, "count": len(rows_), "hasMore": False, "nextCursor": None}
                return storage.sync_partial_page(kind, lambda: listing, progress=report)

    world = services(engine, StoragePulls())
    world.plans.save(ADMIN, plan())
    due(world, engine)
    world.plans.tick(NOW)
    drain(world)
    first = batches(engine, world.scope)[0]
    assert first["phase"] == "completed" and first["created_count"] > 0
    counts = [
        len(rows(engine, f"SELECT id FROM {t}"))
        for t in ("source_customs_declarations", "source_customs_lines")
    ]
    assert rows(engine, "SELECT DISTINCT specification FROM source_customs_lines") == [
        {"specification": None}
    ]

    records.update(original)  # NS 补填了规格型号
    with engine.connect() as connection:
        revision = ns_plan_dao.get(connection, world.scope)["revision"]
    world.plans.save(ADMIN, plan(revision=revision))
    due(world, engine, NOW + timedelta(days=1))
    world.plans.tick(NOW + timedelta(days=1))
    drain(world, NOW + timedelta(days=1))
    second = batches(engine, world.scope)[1]
    assert second["phase"] == "completed"
    assert second["created_count"] == 0 and second["updated_count"] > 0
    after = [
        len(rows(engine, f"SELECT id FROM {t}"))
        for t in ("source_customs_declarations", "source_customs_lines")
    ]
    assert after == counts
    assert rows(engine, "SELECT DISTINCT specification FROM source_customs_lines") == [
        {"specification": "型号"}
    ]


def test_unknown_group_does_not_stop_later_pages(batch, engine, monkeypatch):
    """source 真实提交结果经过持久批次后仍推进下一页，不重发未知组。"""
    ns_, records_page, _, _ = batch
    storage = StorageService(ns_, engine)
    commit = storage.commit
    attempts = []

    def save(*args):
        attempts.append(args[1]["customs"][0][0])
        saved = commit(*args)
        if len(attempts) == 2:
            args[0].invalidate()
            raise OperationalError("", {}, Exception("commit acknowledgement lost"))
        return saved

    monkeypatch.setattr(storage, "commit", save)

    class StoragePulls(Pulls):
        def pull_and_save(self, kind, request, owner):
            self.requests.append((kind, request))
            first = len(self.requests) == 1
            selected = records_page[:3] if first else records_page[3:4]
            listing = {
                "rows": [{**row, "number": row["record"]["name"]} for row in selected],
                "count": len(selected),
                "hasMore": first,
                "nextCursor": {"afterId": selected[-1]["id"], "throughId": None, "offset": 0}
                if first
                else None,
            }
            return storage.sync_partial_page(kind, lambda: listing)

    pulls = StoragePulls()
    world = services(engine, pulls)
    world.plans.save(ADMIN, plan())
    due(world, engine)
    world.plans.tick(NOW)
    drain(world)
    saved = batches(engine, world.scope)[0]
    assert saved["phase"] == "partial"
    assert "待核实" in saved["message"]
    results = pages(engine, saved["id"])
    assert [row["status"] for row in results] == ["partial", "completed"]
    assert results[0]["result"]["batch"]["counts"]["unknown"] == 1
    assert [request.offset for _, request in pulls.requests] == [0, 20]
    assert attempts == [row["id"] for row in records_page[:4]]
    assert len(rows(engine, "SELECT id FROM source_customs_declarations")) == 4
    assert saved["created_count"] == 6  # 未知组的报关及子采购不计入确认成功数。


def test_plan_http_requires_admin_and_validates_body(context, monkeypatch):
    settings = replace(context.settings, origin="https://invoice.example")
    app = create_app(settings, context.ns, context.engine)
    # 本项只验收接口契约，后台消费由上方用例覆盖。
    monkeypatch.setattr(app.state.ns_plan_worker, "start", lambda: None)
    with TestClient(app, base_url=settings.origin) as client:
        client.headers["Origin"] = settings.origin
        assert client.get("/api/sync/ns/plan").status_code == 401
        login(client, settings)
        view = client.get("/api/sync/ns/plan")
        assert view.status_code == 200 and view.json()["plan"]["revision"] == 0
        body = {**plan(enabled=False).model_dump()}
        saved = client.put("/api/sync/ns/plan", json=body)
        assert saved.status_code == 200 and saved.json()["plan"]["revision"] == 1
        assert client.put("/api/sync/ns/plan", json=body).status_code == 409
        for change in ({"kinds": []}, {"times": ["24:00"]}, {"enabled": "yes"}, {"owner": "other"}):
            assert client.put("/api/sync/ns/plan", json={**body, "revision": 1, **change}).status_code == 400
        listing = client.get("/api/sync/ns/batches")
        assert listing.status_code == 200 and listing.json()["total"] == 0
        assert client.get("/api/sync/ns/batches/not-a-uuid").status_code == 400
        missing = client.get("/api/sync/ns/batches/0f8fad5b-d9cb-469f-a165-70867728950e")
        assert missing.status_code == 404
        client.cookies.clear()
        client.headers["Authorization"] = "Bearer " + settings.service_key
        assert client.get("/api/sync/ns/plan").status_code in (401, 403)


def test_migration_downgrade_refused_once_plan_exists(engine):
    from alembic import command
    from backend.manage import SCHEMA_INI, _config

    world = services(engine, Pulls())
    world.plans.save(ADMIN, plan(enabled=False))
    config = _config(SCHEMA_INI, engine.url.render_as_string(hide_password=False))
    with pytest.raises(RuntimeError, match="不能降级删除"):
        command.downgrade(config, "0039_task_wecom_directory")
    assert world.plans.configuration(ADMIN)["plan"]["revision"] == 1
