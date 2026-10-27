"""近 14 天同步情况：NS 批次、后台同步批次、柠檬云手动拉票按北京时间逐日汇总。"""

from datetime import date, datetime, timezone

from backend.modules.sync.entity.lemon_run import lemon_runs
from backend.modules.sync.entity.ns_run import ns_runs
from backend.modules.sync.entity.sync_run import sync_runs
from backend.modules.sync.policy.sync_health_policy import day_status
from backend.modules.sync.service.sync_health_service import SyncHealthService
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from sqlalchemy import insert

# 北京时间 2026-10-27 12:00
NOW = datetime(2026, 10, 27, 4, 0, tzinfo=timezone.utc)
counter = iter(range(1, 1000))


def ns(connection, kind, status, at):
    connection.execute(
        insert(ns_runs).values(
            scope_key="s",
            request_id=f"ns-{next(counter)}",
            kind=kind,
            request={},
            status=status,
            created_at=at,
        )
    )


def batch(connection, phase, at, source="lemon_invoice"):
    connection.execute(
        insert(sync_runs).values(
            source=source, trigger_type="schedule", started_by="scheduler", started_at=at, phase=phase
        )
    )


def manual(connection, status, at, run_id=None):
    connection.execute(
        insert(lemon_runs).values(
            scope_key="s",
            request_id=f"lemon-{next(counter)}",
            asid="a1",
            account_name="账套",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 2),
            status=status,
            run_id=run_id,
            created_at=at,
        )
    )


def test_day_status_rules():
    assert day_status([]) == "none"
    assert day_status(["running"]) == "running"
    assert day_status(["success", "success"]) == "success"
    assert day_status(["failed", "running"]) == "failed"
    assert day_status(["success", "failed"]) == "partial"
    assert day_status(["partial"]) == "partial"


def test_health_groups_runs_by_source_and_beijing_day(engine):
    with engine.begin() as connection:
        # 北京时间 10-27 00:30（UTC 10-26 16:30）计入 10-27
        ns(connection, "customs-declarations", "completed", datetime(2026, 10, 26, 16, 30))
        ns(connection, "customs-declarations", "failed", datetime(2026, 10, 27, 1, 0))
        ns(connection, "sub-purchase-orders", "completed", datetime(2026, 10, 20, 2, 0))
        batch(connection, "completed", datetime(2026, 10, 26, 2, 0))
        manual(connection, "failed", datetime(2026, 10, 25, 2, 0))
        manual(connection, "queued", datetime(2026, 10, 24, 2, 0))  # 排队分片不算一次执行
        ns(connection, "customs-declarations", "completed", datetime(2026, 10, 1, 2, 0))  # 超出 14 天
    result = SyncHealthService(engine).health(now=NOW)
    assert result.dates[0] == "2026-10-14" and result.dates[-1] == "2026-10-27" and len(result.dates) == 14
    rows = {row.key: {day.date: day for day in row.days} for row in result.rows}
    assert [row.label for row in result.rows] == ["NS 报关单", "NS 子采购", "柠檬云发票"]
    today = rows["ns-customs"]["2026-10-27"]
    assert (today.status, today.label, today.runs, today.failed) == ("partial", "部分成功", 2, 1)
    assert rows["ns-purchase"]["2026-10-20"].status == "success"
    assert rows["lemon"]["2026-10-26"].status == "success"
    assert rows["lemon"]["2026-10-25"].status == "failed"
    assert rows["lemon"]["2026-10-24"].status == "none"
    assert sum(day.runs for day in rows["ns-customs"].values()) == 2
