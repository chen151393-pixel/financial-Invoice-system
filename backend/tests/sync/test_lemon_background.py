"""持久队列、账套隔离、失败恢复与每日调度；上游使用替身，不写真实账套。"""

from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from backend.core.errors import ApiError
from backend.modules.invoice.entity import headers, versions
from backend.modules.sync.dao import lemon_plan_dao, lemon_run_dao, sync_run_dao
from backend.modules.sync.dto.lemon_batch_dto import RetryBatch, SavePlan, SubmitBatch
from backend.modules.sync.dto.lemon_invoice_dto import PullLemonInvoices
from backend.modules.sync.policy.lemon_batch_policy import INTERRUPTED, next_time
from backend.modules.sync.service.lemon_batch_service import LemonBatchService
from backend.modules.sync.service.lemon_job_service import LemonJobService
from backend.modules.sync.service.lemon_plan_service import LemonPlanService
from backend.modules.sync.service.lemon_worker import LemonWorker
from backend.tests.sync.test_lemon_invoices import OWNER, count, make_services
from sqlalchemy import text


def request(**changes):
    return SubmitBatch(requestId=str(uuid4()), startDate="2026-10-01", endDate="2026-10-19", **changes)


def plan(**changes):
    return SavePlan(
        **{"revision": 0, "enabled": True, "times": ["02:00", "14:00"], "lookbackDays": 90, **changes}
    )


def background_services(engine, settings):
    accounts, invoices, upstream, events = make_services(engine, settings)
    batches = LemonBatchService(accounts)
    plans = LemonPlanService(batches)
    jobs = LemonJobService(batches, invoices)
    worker = LemonWorker(plans, jobs)
    return SimpleNamespace(
        accounts=accounts,
        invoices=invoices,
        upstream=upstream,
        events=events,
        batches=batches,
        plans=plans,
        jobs=jobs,
        worker=worker,
        engine=engine,
    )


@pytest.fixture
def world(context):
    settings = replace(
        context.settings,
        origin="https://invoice.example",
        lemon_app_id="12345",
        lemon_app_secret="secret",
        lemon_redirect_uri="https://invoice.example/api/lemon/oauth/callback",
    )
    return background_services(context.engine, settings)


def drain(world, request_id, limit=40):
    for _ in range(limit):
        world.worker.run_once()
        result = world.batches.read(OWNER, request_id)
        if not result["poll"]:
            return result
    pytest.fail("任务未在预期分片次数内完成")


def test_submit_is_persistent_no_upstream_and_all_accounts_isolated(world):
    body = request()
    first = world.batches.submit(OWNER, body)
    assert first["phase"] == "queued" and world.upstream.pulls == 0
    assert world.batches.submit(OWNER, body)["requestId"] == first["requestId"]
    with pytest.raises(ApiError, match="不能更改"):
        world.batches.submit(OWNER, body.model_copy(update={"endDate": "2026-10-18"}))
    # 修改页面选择不改变队列的全账套范围。
    world.accounts.select(OWNER, "8")
    result = drain(world, body.requestId)
    assert result["phase"] == "completed" and len(result["accounts"]) == 2
    assert result["created"] == 2 and count(world.engine, headers) == 2
    repeated = request()
    world.batches.submit(OWNER, repeated)
    assert drain(world, repeated.requestId)["created"] == 0
    assert count(world.engine, versions) == 2
    assert world.accounts.configuration(OWNER)["selected"]["asid"] == "8"
    with world.engine.connect() as connection:
        # 分片直接是带批次编号的拉票记录；旧分片表保留在库中但不再写入。
        assert connection.scalar(text("SELECT COUNT(*) FROM sync_lemon_runs WHERE run_id IS NOT NULL")) == 4
        assert connection.scalar(text("SELECT COUNT(*) FROM sync_lemon_jobs")) == 0


def test_one_account_failure_does_not_block_others_and_retry_only_failed(world):
    original = world.upstream.invoices

    def read(token, asid, start, end):
        if asid == "7":
            raise ApiError(403, "账套授权失效")
        return original(token, asid, start, end)

    world.upstream.invoices = read
    body = request()
    world.batches.submit(OWNER, body)
    result = drain(world, body.requestId)
    assert result["phase"] == "partial" and result["failed"] == 1 and result["created"] == 1
    world.upstream.invoices = original
    retry = RetryBatch(requestId=str(uuid4()))
    queued = world.batches.retry(OWNER, body.requestId, retry)
    assert world.batches.retry(OWNER, body.requestId, retry)["requestId"] == queued["requestId"]
    result = drain(world, retry.requestId)
    assert result["phase"] == "completed" and [v["asid"] for v in result["accounts"]] == ["7"]
    assert count(world.engine, headers) == 2


def test_range_limit_splits_without_losing_or_double_counting_dates(world):
    seen = []

    def read(token, asid, start, end):
        seen.append((start, end))
        if start != end:
            raise ApiError(422, "票量超限", code="lemon_range_limit")
        return []

    world.upstream.invoices = read
    body = request(accountMode="selected", accountIds=["7"]).model_copy(
        update={"startDate": "2026-10-01", "endDate": "2026-10-03"}
    )
    world.batches.submit(OWNER, body)
    result = drain(world, body.requestId)
    assert result["phase"] == "completed" and result["failed"] == 0
    assert result["accounts"][0]["total"] == 3
    assert sorted(start for start, end in seen if start == end) == ["2026-10-01", "2026-10-02", "2026-10-03"]


def test_single_day_over_limit_is_explicit_failure(world):
    world.upstream.failure = ApiError(422, "本次超过 2000 张发票", code="lemon_range_limit")
    body = request(accountMode="selected", accountIds=["7"]).model_copy(
        update={"startDate": "2026-10-10", "endDate": "2026-10-10"}
    )
    world.batches.submit(OWNER, body)
    result = drain(world, body.requestId)
    assert result["phase"] == "failed" and result["failed"] == 1


def test_restart_reconciles_committed_results_but_never_reexecutes_unknown(world):
    body = request()
    world.batches.submit(OWNER, body)
    world.worker.run_once()
    with world.engine.begin() as connection:
        batch = sync_run_dao.get(connection, world.worker.scope, body.requestId)
        shard = lemon_run_dao.batch_shards(connection, batch["id"])[0]
        pull = PullLemonInvoices(
            requestId=shard["request_id"],
            asid=shard["asid"],
            startDate=shard["start_date"].isoformat(),
            endDate=shard["end_date"].isoformat(),
        )
        scope, binding = world.accounts.context(connection, OWNER, lock=True)
        world.invoices.claim_background(connection, scope, pull)
    result = drain(world, body.requestId)
    assert result["phase"] == "unknown" and world.upstream.pulls == 1  # 另一账套仍执行。
    interrupted = next(v for v in result["accounts"] if v["asid"] == shard["asid"])["windows"][0]
    assert interrupted["label"] == "结果待核实" and interrupted["error"] == INTERRUPTED
    assert not result["retry"]["allowed"]
    with pytest.raises(ApiError, match="不能重试"):
        world.batches.retry(OWNER, body.requestId, RetryBatch(requestId=str(uuid4())))
    # 模拟原执行器的提交已完成而任务状态响应丢失；重启只核实，无再次读取。
    world.invoices._execute(OWNER, pull, scope, binding, background=True)
    pulls = world.upstream.pulls
    LemonWorker(world.plans, world.jobs).run_once()
    assert world.batches.read(OWNER, body.requestId)["phase"] == "completed"
    assert world.upstream.pulls == pulls


def test_event_failure_rolls_back_and_keeps_failed_task(world):
    from backend.modules.invoice.public import InvoicesImported

    def fail(connection, event):
        raise ApiError(409, "测试订阅拒绝")

    world.events.subscribe(InvoicesImported, fail)
    body = request()
    world.batches.submit(OWNER, body)
    assert drain(world, body.requestId)["phase"] == "failed"
    assert count(world.engine, headers) == count(world.engine, versions) == 0


def test_plan_timezone_revision_pause_and_downtime_coalescing(world):
    result = world.plans.save(OWNER, plan())
    with pytest.raises(ApiError, match="已被修改"):
        world.plans.save(OWNER, plan())
    now = datetime(2026, 10, 20, 0, 0)
    with world.engine.begin() as connection:
        lemon_plan_dao.save(connection, world.worker.scope, {"next_run_at": now - timedelta(days=3)})
    world.plans.tick(OWNER, now)
    world.plans.tick(OWNER, now)
    records = world.batches.list(OWNER)
    assert records["total"] == 1
    assert records["items"][0]["startDate"] == "2026-07-23"
    assert records["items"][0]["endDate"] == "2026-10-20"
    with world.engine.connect() as connection:
        row = lemon_plan_dao.get(connection, world.worker.scope)
    assert row["next_run_at"] == datetime(2026, 10, 20, 6, 0)
    assert next_time(["02:00"], datetime(2026, 10, 19, 18, 0)) == datetime(2026, 10, 20, 18, 0)
    world.plans.save(OWNER, plan(revision=result["plan"]["revision"], enabled=False))
    world.plans.tick(OWNER, now + timedelta(days=10))
    assert world.batches.list(OWNER)["total"] == 1


def test_selected_revoked_account_and_all_exclusions(world):
    body = request(accountMode="selected", accountIds=["999", "8"])
    world.batches.submit(OWNER, body)
    assert drain(world, body.requestId)["phase"] == "partial"
    body = request(excludedIds=["7"])
    world.batches.submit(OWNER, body)
    result = drain(world, body.requestId)
    assert [v["asid"] for v in result["accounts"]] == ["8"]
    with pytest.raises(ApiError, match="管理员"):
        world.batches.read("user:other", body.requestId)


def test_history_splits_into_bounded_windows_and_freezes_conditions(world):
    world.upstream.rows = []
    body = request(accountMode="selected", accountIds=["7"]).model_copy(
        update={"startDate": "2025-01-01", "endDate": "2026-10-19"}
    )
    world.batches.submit(OWNER, body)
    world.worker.run_once()
    detail = world.batches.read(OWNER, body.requestId)
    periods = detail["accounts"][0]["windows"]
    assert (
        len(periods) > 12
        and periods[0]["startDate"] == "2025-01-01"
        and periods[-1]["endDate"] == "2026-10-19"
    )
    assert all(v["label"] == "等待执行" for v in periods)


def test_discovery_failure_and_empty_accounts_are_not_success(world):
    world.upstream.allowed = []
    body = request()
    world.batches.submit(OWNER, body)
    result = drain(world, body.requestId)
    assert result["phase"] == "failed" and "没有可纳入" in result["message"]


def test_configuration_secrets_not_exposed(world):
    result = world.plans.save(OWNER, plan())
    assert "bindingKey" not in str(result) and "13800000001" not in str(result)
    assert result["submit"]["allowed"]


def test_stale_consumer_cannot_repeat_discovery_or_finished_job(world):
    body = request()
    world.batches.submit(OWNER, body)
    with world.engine.connect() as connection:
        batch = sync_run_dao.get(connection, world.worker.scope, body.requestId)
    world.jobs.discover(batch)
    world.jobs.discover(batch)
    with world.engine.connect() as connection:
        rows = lemon_run_dao.batch_shards(connection, batch["id"])
    assert len(rows) == 2
    shard = rows[0]
    world.jobs.execute(batch, shard)
    pulls = world.upstream.pulls
    world.jobs.execute(batch, shard)
    world.jobs._refuse(shard, "过期消费者不能覆盖提交结果")
    assert world.upstream.pulls == pulls
    with world.engine.connect() as connection:
        assert lemon_run_dao.get(connection, batch["scope_key"], shard["request_id"])["status"] == "completed"
