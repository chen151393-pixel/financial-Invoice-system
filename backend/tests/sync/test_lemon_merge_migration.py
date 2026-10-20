"""0025：分片并入 sync_lemon_runs、sync_runs 精简重复列；带数据升级不丢事实，无法还原时中止。"""

import json

import pytest
from backend.manage import upgrade_schema
from backend.tests.test_schema_baseline import NOW, insert
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from sqlalchemy import inspect, text

INITIAL_REVISION = "0024_sync_ns_runs"
SCOPE = "scope-a"


def _batch(connection, request_id="batch-1", **changes):
    values = {
        "source": "lemon_invoice",
        "account": SCOPE,
        "trigger_type": "manual",
        "status": "running",
        "started_by": "user:admin",
        "started_at": NOW,
        "scope_key": SCOPE,
        "request_id": request_id,
        "phase": "unknown",
        "configuration": json.dumps(
            {"startDate": "2026-10-01", "endDate": "2026-10-19", "businessTypes": ["专票"]}
        ),
        "window_start": "2026-10-01 00:00:00",
        "window_end": "2026-10-19 00:00:00",
        **changes,
    }
    return insert(connection, "sync_runs", **values)


def _shard(connection, run_id, request_id, status, error=None):
    insert(
        connection,
        "sync_lemon_jobs",
        run_id=run_id,
        request_id=request_id,
        asid="7",
        account_name="账套七",
        start_date="2026-10-01",
        end_date="2026-10-19",
        status=status,
        error=error,
    )


def _pull(connection, request_id, status, background=True, error=None):
    insert(
        connection,
        "sync_lemon_runs",
        scope_key=SCOPE,
        request_id=request_id,
        asid="7",
        account_name="账套七",
        start_date="2026-10-01",
        end_date="2026-10-19",
        status=status,
        result=json.dumps({"businessTypes": ["专票"], "invoiceIds": [], "created": 1}),
        error=error,
        background=background,
    )


def _rows(connection):
    query = "SELECT request_id, status, run_id, error FROM sync_lemon_runs ORDER BY request_id"
    return {row.request_id: row for row in connection.execute(text(query))}


def test_shards_merge_into_pulls_and_batch_columns_shrink(schema_engine):
    with schema_engine.begin() as connection:
        run_id = _batch(connection)
        for request_id, status, error in (
            ("r-queued", "queued", None),
            ("r-done", "completed", None),
            ("r-split", "split", None),
            ("r-refused", "failed", "授权绑定已变化"),
            ("r-unknown", "unknown", "执行曾中断，提交结果待核实；禁止直接重试"),
        ):
            _shard(connection, run_id, request_id, status, error)
        _pull(connection, "r-done", "completed")
        _pull(connection, "r-split", "failed", error="票量超限")
        _pull(connection, "r-unknown", "running")
        _pull(connection, "r-manual", "completed", background=False)
    upgrade_schema(schema_engine.url.render_as_string(hide_password=False))
    with schema_engine.connect() as connection:
        rows = _rows(connection)
        result = connection.execute(
            text("SELECT result FROM sync_lemon_runs WHERE request_id = 'r-queued'")
        ).scalar()
        assert connection.execute(text("SELECT COUNT(*) FROM sync_lemon_jobs")).scalar() == 5
    assert {key: row.status for key, row in rows.items()} == {
        "r-done": "completed",
        "r-manual": "completed",
        "r-queued": "queued",
        "r-refused": "failed",
        "r-split": "split",
        "r-unknown": "running",
    }
    assert rows["r-manual"].run_id is None
    assert {row.run_id for key, row in rows.items() if key != "r-manual"} == {run_id}
    assert rows["r-split"].error == "票量超限" and rows["r-refused"].error == "授权绑定已变化"
    assert rows["r-unknown"].error is None
    assert json.loads(result) == {"businessTypes": ["专票"], "invoiceIds": []}
    columns = {c["name"]: c for c in inspect(schema_engine).get_columns("sync_runs")}
    assert not {"status", "account", "window_start", "window_end"} & set(columns)
    assert not columns["phase"]["nullable"]
    assert "background" not in {c["name"] for c in inspect(schema_engine).get_columns("sync_lemon_runs")}


@pytest.mark.parametrize(
    "changes",
    [{"account": "another-scope"}, {"window_end": "2026-10-18 00:00:00"}, {"phase": None}],
)
def test_unrecoverable_batch_columns_abort_before_any_change(schema_engine, changes):
    with schema_engine.begin() as connection:
        _batch(connection, **changes)
    with pytest.raises(RuntimeError, match="无法由 phase"):
        upgrade_schema(schema_engine.url.render_as_string(hide_password=False))
    assert "run_id" not in {c["name"] for c in inspect(schema_engine).get_columns("sync_lemon_runs")}
    assert "status" in {c["name"] for c in inspect(schema_engine).get_columns("sync_runs")}


def test_background_pull_without_shard_aborts(schema_engine):
    with schema_engine.begin() as connection:
        _pull(connection, "r-orphan", "completed")
    with pytest.raises(RuntimeError, match="找不到所属分片"):
        upgrade_schema(schema_engine.url.render_as_string(hide_password=False))
    assert "run_id" not in {c["name"] for c in inspect(schema_engine).get_columns("sync_lemon_runs")}
