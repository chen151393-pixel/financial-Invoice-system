"""数据同步中心合并执行记录：NS 与柠檬云批次同一列表，按执行时间倒序，可按来源与状态筛选。"""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from backend.core.errors import ApiError
from backend.modules.sync.dao import sync_run_dao
from backend.modules.sync.service.sync_history_service import SyncHistoryService
from backend.tests.sync.test_ns_history import NOW, manual, scheduled
from backend.tests.sync.test_ns_plan import ADMIN, Pulls, services
from backend.tests.sync.test_ns_runs import engine as engine

LEMON_SCOPE = "lemon-scope"


def lemon_batch(engine, request_id, at, phase="completed", scope=LEMON_SCOPE):
    with engine.begin() as connection:
        sync_run_dao.create(
            connection,
            {
                "scope_key": scope,
                "request_id": request_id,
                "source": "lemon_invoice",
                "trigger_type": "schedule",
                "started_by": ADMIN,
                "started_at": at,
                "phase": phase,
                "fetched_count": 54,
                "created_count": 0,
                "updated_count": 0,
                "failed_count": 0,
                "configuration": {
                    "startDate": "2026-10-21",
                    "endDate": "2026-10-30",
                    "businessTypes": ["采购支出"],
                    "accountMode": "all",
                },
            },
        )


def history(engine):
    world = services(engine, Pulls())
    lemon = SimpleNamespace(scope=lambda owner: LEMON_SCOPE)
    return world, SyncHistoryService(engine, world.batches, lemon)


def test_merges_ns_and_lemon_by_execution_time_desc(engine):
    world, service = history(engine)
    plan_id = str(uuid4())
    scheduled(engine, world, plan_id, NOW - timedelta(minutes=2))
    manual_id = manual(engine, world, at=NOW)
    lemon_id = str(uuid4())
    lemon_batch(engine, lemon_id, NOW - timedelta(minutes=1))
    lemon_batch(engine, str(uuid4()), NOW, scope="other-binding")  # 其他绑定的批次不出现

    result = service.list(ADMIN)

    assert [row["requestId"] for row in result["items"]] == [manual_id, lemon_id, plan_id]
    assert [row["source"] for row in result["items"]] == ["ns", "lemon", "ns"]
    lemon = result["items"][1]
    assert lemon["recordType"] == "lemon" and lemon["rangeLabel"] == "开票日期"
    assert lemon["startDate"] == "2026-10-21" and lemon["fetched"] == 54
    assert result["total"] == 3 and result["counts"] == {"completed": 3}
    assert set(result["plans"]) == {"ns", "lemon"}


def test_filters_by_source_phase_and_paginates(engine):
    world, service = history(engine)
    scheduled(engine, world, str(uuid4()), NOW - timedelta(minutes=3))
    lemon_batch(engine, str(uuid4()), NOW - timedelta(minutes=2))
    failed_id = str(uuid4())
    lemon_batch(engine, failed_id, NOW - timedelta(minutes=1), phase="failed")

    only_lemon = service.list(ADMIN, source="lemon")
    assert only_lemon["total"] == 2
    assert {row["source"] for row in only_lemon["items"]} == {"lemon"}
    only_ns = service.list(ADMIN, source="ns")
    assert only_ns["total"] == 1 and only_ns["items"][0]["source"] == "ns"
    failed = service.list(ADMIN, phase="failed")
    assert [row["requestId"] for row in failed["items"]] == [failed_id]
    second = service.list(ADMIN, page=2, size=2)
    assert second["pages"] == 2 and len(second["items"]) == 1 and second["items"][0]["source"] == "ns"


def test_requires_admin(engine):
    _, service = history(engine)
    with pytest.raises(ApiError) as error:
        service.list("user:someone")
    assert error.value.status == 403
