"""旧待审建议升级：只读整单预览、审核封口、重生成替换及历史保护（隔离 SQLite）。"""

from copy import deepcopy
from decimal import Decimal

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.matching.dao import allocation_dao
from backend.modules.matching.dto.matching_dto import BatchBody, ConfirmBody, GroupConfirmBody, QueueQuery
from backend.modules.matching.policy.pending_order_policy import REGENERATE, whole_order
from backend.modules.matching.service import group_plan_service, proposal_service
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import group, proposals
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_matching_manual_order import SHORT, target, task_lines
from backend.tests.test_task import USER
from fastapi.testclient import TestClient
from sqlalchemy import text


def saved(engine, invoice_id):
    with engine.connect() as connection:
        return allocation_dao.by_invoices(connection, [invoice_id])


def make_legacy(engine, invoice_id, *, grouped=False, mixed=False):
    """模拟升级前的已保存建议，不通过新代码生成旧规则数据。"""
    before = saved(engine, invoice_id)
    with engine.begin() as connection:
        for index, row in enumerate(before):
            checks = deepcopy(row["checks"])
            if not mixed or index == 0:
                checks.pop("orderShare", None)
            if not grouped:
                checks.pop("group", None)
            for check in checks["items"]:
                if check["key"] in ("quantity", "amount"):
                    check.update(result="match", note="本次在剩余应开范围内可分次收票")
            allocation_dao.update_status(
                connection, row["id"], {"checks": checks, "confidence": Decimal(100)}, row["updated_at"]
            )
    return before


def legacy_invoice(world, engine, *, grouped=False, mixed=False):
    invoice_id, _ = target(world, engine, "26000000000000009801", SHORT, keep_proposal=True)
    make_legacy(engine, invoice_id, grouped=grouped, mixed=mixed)
    return invoice_id


@pytest.mark.parametrize("grouped,mixed", [(False, False), (True, False), (True, True)])
def test_legacy_preview_is_whole_order_and_all_review_paths_block(engine, world, reviewed, grouped, mixed):
    invoice_id = legacy_invoice(world, engine, grouped=grouped, mixed=mixed)
    before = saved(engine, invoice_id)
    view = world["queries"].invoice(invoice_id)
    pending = proposals(world, invoice_id)
    for row in pending:
        checks = {check.key: check for check in row.checks}
        assert checks["quantity"].purchaseValue == "20"  # 两条整单明细，不能只取旧分配的 4 个
        assert checks["quantity"].differenceLabel == "发票少 16"
        assert checks["amount"].differenceLabel == "发票少 80.30"
        assert checks["quantity"].resultLabel == checks["amount"].resultLabel == "不一致"
        assert not row.confirm.allowed and row.confirm.reason == REGENERATE
        with pytest.raises(ApiError) as error:
            world["allocations"].confirm(int(row.id), ConfirmBody(note="填写说明也不能绕过"), USER)
        assert error.value.status == 409
    if grouped:
        (found,) = view.groups
        assert not found.confirm.allowed and found.confirm.reason == REGENERATE
        assert all(check.resultLabel != "分次收票" for item in found.items for check in item.checks)
        with pytest.raises(ApiError, match="旧待审建议"):
            world["allocations"].confirm_group(
                found.id, GroupConfirmBody(invoiceId=str(invoice_id), note="确认"), USER
            )
    queue = world["queries"].invoice_queue(QueueQuery())
    assert not queue.rows[0].batch.allowed and not queue.rows[0].batchIds
    result = world["allocations"].confirm_batch(BatchBody(ids=[row.id for row in pending]), USER)
    assert result["confirmed"] == 0 and len(result["skipped"]) == len(pending)
    assert saved(engine, invoice_id) == before
    assert all(row["received_amount"] == 0 for row in task_lines(engine))


@pytest.mark.parametrize("grouped", [False, True])
def test_regenerate_replaces_legacy_and_short_invoice_closes_atomically(engine, world, reviewed, grouped):
    invoice_id = legacy_invoice(world, engine, grouped=grouped)
    old = saved(engine, invoice_id)
    assert world["proposals"].generate_now([invoice_id], USER) == 2
    current = saved(engine, invoice_id)
    retired = [row for row in current if row["id"] in {old_row["id"] for old_row in old}]
    assert all(row["status"] == "rejected" and row["reviewed_by"] == USER for row in retired)
    assert all("整单规则升级" in row["review_note"] for row in retired)
    assert [row["checks"] for row in retired] == [row["checks"] for row in old]
    assert all(whole_order(row) for row in current if row["status"] == "proposed")
    assert world["proposals"].generate_now([invoice_id], USER) == 0
    assert saved(engine, invoice_id) == current
    found = group(world, invoice_id)
    body = GroupConfirmBody(invoiceId=str(invoice_id))
    with pytest.raises(ApiError, match="请填写审核说明"):
        world["allocations"].confirm_group(found.id, body, USER)
    assert saved(engine, invoice_id) == current
    body = body.model_copy(update={"note": "整单少开，差额核实后结束"})
    world["allocations"].confirm_group(found.id, body, USER)
    confirmed = saved(engine, invoice_id)
    assert all(row["closed_with_difference"] for row in task_lines(engine))
    world["allocations"].confirm_group(found.id, body, USER)
    assert saved(engine, invoice_id) == confirmed


def test_no_candidate_retires_legacy_instead_of_leaving_it_reviewable(engine, world, reviewed):
    invoice_id = legacy_invoice(world, engine, grouped=True)
    with engine.begin() as connection:
        connection.execute(text("UPDATE task_lines SET status = 'superseded'"))
    pending = proposals(world, invoice_id)
    assert all(not row.checks and not row.confirm.allowed for row in pending)
    assert world["proposals"].generate_now([invoice_id], USER) == 0
    assert not proposals(world, invoice_id) and not world["queries"].invoice(invoice_id).groups
    assert all(row["status"] == "rejected" for row in saved(engine, invoice_id))


def test_old_single_line_preview_includes_unsuggested_order_lines(engine, world, reviewed):
    invoice_id = legacy_invoice(world, engine)
    second = saved(engine, invoice_id)[1]
    with engine.begin() as connection:
        allocation_dao.update_status(connection, second["id"], {"status": "rejected"}, second["updated_at"])
    (pending,) = proposals(world, invoice_id)
    quantity = next(check for check in pending.checks if check.key == "quantity")
    assert quantity.purchaseValue == "20" and quantity.differenceLabel == "发票少 16"
    assert world["proposals"].generate_now([invoice_id], USER) == 2
    assert len(proposals(world, invoice_id)) == 2


def test_regenerate_failure_rolls_back_legacy_retirement(engine, world, reviewed, monkeypatch):
    invoice_id = legacy_invoice(world, engine)
    before = saved(engine, invoice_id)
    insert = allocation_dao.insert_allocation
    count = 0

    def fail_second(*args):
        nonlocal count
        count += 1
        if count == 2:
            raise ApiError(409, "模拟第二行写入失败")
        return insert(*args)

    monkeypatch.setattr(allocation_dao, "insert_allocation", fail_second)
    with pytest.raises(ApiError, match="第二行写入失败"):
        world["proposals"].generate_now([invoice_id], USER)
    assert saved(engine, invoice_id) == before


def test_import_does_not_migrate_legacy_and_confirmed_history_stays_unchanged(engine, world, reviewed):
    invoice_id = legacy_invoice(world, engine)
    before = saved(engine, invoice_id)
    with engine.begin() as connection:
        assert proposal_service.generate(connection, [invoice_id], USER) == 0
    assert saved(engine, invoice_id) == before
    # 模拟升级前已确认的一组记录；查询/重生成不得改写其快照、历史或审计字段。
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE matching_allocations SET status = 'confirmed', reviewed_by = :actor"),
            {"actor": USER},
        )
    confirmed = saved(engine, invoice_id)
    view = world["queries"].invoice(invoice_id)
    assert any(check.resultLabel == "分次收票" for row in view.items[0].allocations for check in row.checks)
    assert world["proposals"].generate_now([invoice_id], USER) == 0
    assert saved(engine, invoice_id) == confirmed


def test_snapshot_change_invalidates_unchanged_comparison(engine, world, reviewed, monkeypatch):
    invoice_id, _ = target(world, engine, "26000000000000009802", SHORT, keep_proposal=True)
    original = group_plan_service.plan

    def change_share(*args):
        result = original(*args)
        result[0]["rows"][0]["share_amount"] += Decimal("1")
        return result

    monkeypatch.setattr(group_plan_service, "plan", change_share)
    assert world["proposals"].generate_now([invoice_id], USER) == 2


def test_http_stale_page_cannot_confirm_legacy(context, engine, world, reviewed):
    invoice_id = legacy_invoice(world, engine, grouped=True)
    found = group(world, invoice_id)
    app = create_app(context.settings, context.ns, engine)
    with TestClient(app) as client:
        headers = {"Origin": context.settings.origin}
        assert (
            client.post(
                "/api/session",
                headers=headers,
                json={"username": "admin", "password": context.settings.admin_password},
            ).status_code
            == 200
        )
        for url, body in [
            (f"/api/matching/allocations/{found.allocationIds[0]}/confirm", {"note": "确认"}),
            (f"/api/matching/groups/{found.id}/confirm", {"invoiceId": str(invoice_id), "note": "确认"}),
        ]:
            response = client.post(url, headers=headers, json=body)
            assert response.status_code == 409 and "旧待审建议" in response.json()["error"]
        response = client.post(
            "/api/matching/allocations/confirm-batch", headers=headers, json={"ids": found.allocationIds}
        )
        assert response.status_code == 200 and response.json()["confirmed"] == 0
        response = client.post(
            "/api/matching/proposals/generate", headers=headers, json={"invoiceIds": [str(invoice_id)]}
        )
        assert response.status_code == 200 and response.json()["created"] == 2
