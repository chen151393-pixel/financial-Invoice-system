"""列表单张/批量补拉：范围隔离、幂等、部分明细展示和失败原子性。"""

from copy import deepcopy
from uuid import uuid4

import pytest
from backend.core.errors import ApiError
from backend.modules.invoice.entity import headers, items, versions
from backend.tests.sync.lemon_detail_fixtures import full_invoice
from backend.tests.sync.test_lemon_invoices import BASE, body, count
from backend.tests.sync.test_lemon_invoices import setup as setup
from sqlalchemy import select, update


@pytest.fixture
def seeded(setup):
    upstream = setup.upstream
    upstream.allowed[0]["edition"] = "professional"
    upstream.professional_accounts = lambda token: deepcopy(upstream.allowed)
    upstream.professional_invoices = upstream.invoices
    upstream.rows = [
        {key: value for key, value in full_invoice(InvoiceId=i, Number=str(i)).items() if key != "Detail"}
        for i in range(1, 4)
    ]
    assert setup.client.post(BASE + "/invoices/pull-save", json=body()).status_code == 200
    with setup.engine.connect() as connection:
        ids = [str(value) for value in connection.scalars(select(headers.c.id).order_by(headers.c.id))]
    upstream.rows = [full_invoice(InvoiceId=i, Number=str(i)) for i in range(1, 4)]
    setup.ids = ids
    return setup


def refresh(world, ids=None, request_id=None):
    return world.client.post(
        BASE + "/invoices/refresh-details",
        json={
            "invoiceIds": ids or world.ids[:1],
            "requestId": request_id or str(uuid4()),
        },
    )


def test_single_then_batch_only_changes_selected_and_replays_result(seeded):
    request_id = str(uuid4())
    response = refresh(seeded, request_id=request_id)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["result"]["completeDetails"] == result["result"]["updated"] == 1
    assert result["result"]["fetched"] == 1
    assert count(seeded.engine, items) == 1
    calls = seeded.upstream.pulls
    assert refresh(seeded, request_id=request_id).json() == result
    assert seeded.upstream.pulls == calls
    assert refresh(seeded, seeded.ids[1:], request_id).status_code == 409
    assert refresh(seeded, seeded.ids[1:]).json()["result"]["completeDetails"] == 2
    assert count(seeded.engine, headers) == count(seeded.engine, items) == 3
    assert count(seeded.engine, versions) == 6
    assert refresh(seeded, seeded.ids).json()["result"]["unchanged"] == 3


@pytest.mark.parametrize("field", ["unit", "quality", "name"])
def test_pending_lines_are_visible_after_header_only_import(seeded, field):
    seeded.upstream.rows[0]["Detail"]["invoiceEntries"][0][field] = None
    result = refresh(seeded).json()["result"]
    assert result["pendingDetails"] == 1 and result["completeDetails"] == 0
    assert "缺少" in result["detailIssues"][0]["reason"]
    detail = seeded.client.get("/api/invoices/" + seeded.ids[0]).json()
    assert len(detail["lines"]) == 1 and "待补齐" in detail["detailStatusLabel"]
    assert refresh(seeded).json()["result"]["unchanged"] == 1
    assert count(seeded.engine, versions) == 4


def test_empty_response_explains_unchanged_result(seeded):
    seeded.upstream.rows[0]["Detail"]["invoiceEntries"] = []
    result = refresh(seeded).json()["result"]
    assert result["unchanged"] == 1 and result["detailIssueCount"] == 1
    assert "空商品行" in result["detailIssues"][0]["reason"]
    assert count(seeded.engine, items) == 0


@pytest.mark.parametrize(
    "change,reason", [("source", "仅支持"), ("account", "原账套"), ("missing", "不存在")]
)
def test_actions_and_submit_reject_wrong_scope(seeded, change, reason):
    ids = seeded.ids[:1]
    if change == "missing":
        ids = ["99999"]
    else:
        values = {"source": "lemon_excel"} if change == "source" else {"lemon_account": "another"}
        with seeded.engine.begin() as connection:
            connection.execute(update(headers).where(headers.c.id == int(ids[0])).values(**values))
    actions = seeded.client.post(BASE + "/invoices/detail-actions", json={"invoiceIds": ids}).json()
    assert not actions["rows"][0]["allowed"] and reason in actions["rows"][0]["reason"]
    calls = seeded.upstream.pulls
    assert refresh(seeded, ids).status_code in (404, 409)
    assert seeded.upstream.pulls == calls


@pytest.mark.parametrize("ids", [[], ["1", "1"], ["0"], [1], [str(i) for i in range(1, 102)]])
def test_selection_validation(seeded, ids):
    response = seeded.client.post(
        BASE + "/invoices/refresh-details", json={"invoiceIds": ids, "requestId": str(uuid4())}
    )
    assert response.status_code == 400


def test_missing_upstream_target_or_invalid_line_rolls_back_batch(seeded):
    seeded.upstream.rows.pop()
    assert refresh(seeded, seeded.ids).status_code == 409
    seeded.upstream.rows[1]["Detail"]["invoiceEntries"][0]["tax"] = "99"
    assert refresh(seeded, seeded.ids[:2]).status_code == 422
    assert count(seeded.engine, items) == 0 and count(seeded.engine, versions) == 3


def test_failure_is_persisted_and_repeat_does_not_call_upstream(seeded):
    seeded.upstream.failure = ApiError(502, "测试上游失败")
    request_id = str(uuid4())
    assert refresh(seeded, request_id=request_id).status_code == 502
    calls = seeded.upstream.pulls
    assert refresh(seeded, request_id=request_id).json()["status"] == "failed"
    assert seeded.upstream.pulls == calls and count(seeded.engine, versions) == 3


def test_change_during_network_read_is_rejected(seeded):
    def changed(token, asid, records, selected_ids, professional):
        with seeded.engine.begin() as connection:
            connection.execute(
                update(headers).where(headers.c.id == int(seeded.ids[0])).values(current_version_id=999)
            )
        return records

    seeded.upstream.invoice_details = changed
    response = refresh(seeded)
    assert response.status_code == 409 and "版本已变化" in response.json()["error"]
    assert count(seeded.engine, items) == 0


def test_unauthenticated_selection_is_rejected(seeded):
    seeded.client.cookies.clear()
    assert refresh(seeded).status_code == 401
