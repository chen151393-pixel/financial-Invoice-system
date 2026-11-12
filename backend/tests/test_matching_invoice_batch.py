"""批量审核的 100% 门槛、整票事务、页面快照、逐票结果与权限；仅使用隔离 SQLite。"""

from copy import deepcopy

import pytest
from backend.core.dependencies import current_owner
from backend.core.errors import ApiError
from backend.modules.matching.controller.matching_controller import create_router
from backend.modules.matching.dto.invoice_batch_dto import InvoiceBatchBody
from backend.modules.matching.dto.matching_dto import BatchBody, QueueQuery
from backend.tests.invoice_files import invoice
from backend.tests.matching_batch_helpers import complete_buyer
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import rows
from backend.tests.test_task import USER
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

NUMBER = "26000000000000009801"


def request(row):
    return {
        "invoiceId": row.invoice.id,
        "invoiceVersionId": row.invoice.versionId,
        "allocationIds": row.batchIds,
    }


@pytest.fixture
def ready(engine, world, reviewed):
    import_invoices(world, [invoice(NUMBER, [INK, FLUID], remark="SUB-200")])
    complete_buyer(engine, world, invoice_id(engine, NUMBER))
    row = world["queries"].invoice_queue(QueueQuery()).rows[0]
    assert row.confidence == "100" and row.batch.allowed
    return request(row)


def submit(world, *items, note=""):
    return world["allocations"].confirm_invoice_batch(InvoiceBatchBody(items=list(items), note=note), USER)


def confirmed(engine):
    return rows(engine, "SELECT * FROM matching_allocations WHERE status='confirmed'")


def test_whole_invoice_success_replay_and_ledger(engine, world, ready):
    result = submit(world, ready, note="批量核实")
    assert result == {"approved": [{"id": ready["invoiceId"]}], "skipped": []}
    before = confirmed(engine)
    assert len(before) == 2 and all(row["review_note"] == "批量核实" for row in before)
    assert all(row["reviewed_by"] == USER for row in before)
    assert world["queries"].invoice_queue(QueueQuery()).total == 0
    assert submit(world, ready) == result
    assert confirmed(engine) == before
    assert sum(float(row["received_amount"]) for row in rows(engine, "SELECT * FROM task_lines")) == 120.5


@pytest.mark.parametrize("confidence", ["99.99", "95", "80", None])
def test_nonperfect_blocked_in_queue_and_both_batch_routes(engine, world, ready, confidence):
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE matching_allocations SET confidence=:score WHERE status='proposed'"),
            {"score": confidence},
        )
    row = world["queries"].invoice_queue(QueueQuery()).rows[0]
    assert not row.batch.allowed and not row.batchIds
    result = submit(world, ready, note="填写说明也不能绕过100%")
    assert not result["approved"] and "100%" in result["skipped"][0]["reason"]
    legacy = world["allocations"].confirm_batch(BatchBody(ids=ready["allocationIds"]), USER)
    assert legacy["confirmed"] == 0 and not confirmed(engine)


def test_recalculate_current_confidence_not_only_saved_score(engine, world, ready):
    with engine.begin() as connection:
        connection.execute(text("UPDATE invoice_headers SET buyer_name=NULL, buyer_name_normalized=NULL"))
    result = submit(world, ready)
    assert "100%" in result["skipped"][0]["reason"] and not confirmed(engine)


@pytest.mark.parametrize("change", ["missing", "foreign", "version", "processed", "source"])
def test_stale_or_incomplete_selection_is_skipped_atomically(engine, world, ready, change):
    body = deepcopy(ready)
    if change == "missing":
        body["allocationIds"].pop()
    elif change == "foreign":
        body["allocationIds"][0] = "999999"
    elif change == "version":
        body["invoiceVersionId"] = "999999"
    else:
        with engine.begin() as connection:
            if change == "processed":
                connection.execute(
                    text("UPDATE matching_allocations SET status='rejected' WHERE id=:id"),
                    {"id": int(body["allocationIds"][0])},
                )
            else:
                connection.execute(text("UPDATE source_purchase_order_lines SET unit='箱'"))
    result = submit(world, body)
    assert not result["approved"] and len(result["skipped"]) == 1 and not confirmed(engine)


def test_failed_second_line_rolls_back_first_and_does_not_block_next_invoice(
    engine, world, ready, monkeypatch
):
    original = world["allocations"]._publish
    calls = []

    def fail_second(*args):
        calls.append(1)
        if len(calls) == 2:
            raise ApiError(409, "第二条依据变化")
        return original(*args)

    monkeypatch.setattr(world["allocations"], "_publish", fail_second)
    result = submit(world, ready)
    assert result["skipped"][0]["reason"] == "第二条依据变化" and not confirmed(engine)
    # 无效票跳过后，后续合法票仍可完成；失败票没有残留的收票占用。
    monkeypatch.setattr(world["allocations"], "_publish", original)
    bad = {**ready, "invoiceId": "999999"}
    result = submit(world, bad, ready)
    assert len(result["approved"]) == len(result["skipped"]) == 1
    assert len(confirmed(engine)) == 2


def test_service_identity_denied_and_database_failure_stops_batch(world, ready, monkeypatch):
    body = InvoiceBatchBody(items=[ready])
    with pytest.raises(ApiError, match="服务身份"):
        world["allocations"].confirm_invoice_batch(body, "service:bot")
    calls = []

    def unavailable(*args):
        calls.append(1)
        raise ApiError(503, "数据库不可用")

    monkeypatch.setattr(world["allocations"], "_run", unavailable)
    with pytest.raises(ApiError, match="数据库不可用"):
        submit(world, ready, {**ready, "invoiceId": "999999"})
    assert len(calls) == 1


def test_batch_dto_rejects_empty_duplicate_and_over_limit(ready):
    invalid = [
        [],
        [ready, ready],
        [{**ready, "allocationIds": []}],
        [{**ready, "allocationIds": ready["allocationIds"] * 2}],
        [{**ready, "invoiceId": str(i + 1)} for i in range(51)],
    ]
    for items in invalid:
        with pytest.raises(ValidationError):
            InvoiceBatchBody(items=items)


def test_http_batch_uses_typed_invoice_contract(world, ready):
    app = FastAPI()
    app.include_router(create_router(world["queries"], world["allocations"], world["proposals"], None))
    app.dependency_overrides[current_owner] = lambda: USER
    # 不启动应用后台同步线程；只验证真实路由与真实审核服务。
    with TestClient(app) as client:
        response = client.post("/api/matching/invoice-queue/confirm-batch", json={"items": [ready]})
        assert response.status_code == 200, response.text
        assert response.json() == {"approved": [{"id": ready["invoiceId"], "reason": ""}], "skipped": []}
