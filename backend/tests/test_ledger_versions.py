"""4d 完整链路：不可变版本、真实台账、失效占用和事务回滚。"""

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from backend.core.errors import ApiError
from backend.modules.matching.dto.matching_dto import (
    CancelBody,
    CandidateQuery,
    ConfirmBody,
    ManualBody,
    ReplaceBody,
)
from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
from backend.modules.task.dto.task_dto import ClosureRequest
from backend.modules.task.service.closure_service import ClosureService
from backend.tests.documents_ready import complete_documents
from backend.tests.invoice_files import invoice
from backend.tests.matching_helpers import confirm_groups
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id, proposals, task
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import PARENT, bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_task import USER, approve
from sqlalchemy.exc import SQLAlchemyError


def active_lines(engine):
    return rows(engine, "SELECT * FROM task_lines WHERE status <> 'superseded' ORDER BY purchase_line_id")


def confirm_all(engine, world, number="26000000000000008801"):
    import_invoices(world, [invoice(number, [INK, FLUID], remark="SUB-200")])
    target = invoice_id(engine, number)
    found = proposals(world, target)
    confirm_groups(world, target, USER)
    return target, found


def test_completed_basis_change_rebuilds_from_ledger_and_cancel_reopens(ns, engine, world, reviewed):
    complete_documents(engine)  # 完结需资料齐全；本测试关注收票与账本
    target, found = confirm_all(engine, world)
    assert task(engine)["status"] == "completed"
    original = rows(engine, "SELECT * FROM matching_allocations WHERE status='confirmed'")
    save(ns, engine, bundle([purchase(amounts=("120.50", "20.00"))], [customs("870")]))
    assert active_lines(engine)[0]["requires_review"]
    assert Decimal(str(active_lines(engine)[0]["received_amount"])) == 0
    approve(world, "CD870")
    assert task(engine)["id"] != reviewed["id"]
    assert json.loads(task(engine)["predecessor_task_ids"]) == [reviewed["id"]]
    first, second = active_lines(engine)
    assert Decimal(str(first["received_amount"])) == Decimal("100.5")
    assert first["status"] == "partial" and second["status"] == "received"
    after = rows(engine, "SELECT * FROM matching_allocations WHERE status='confirmed'")
    assert [(r["reviewed_at"], r["purchase_basis_id"]) for r in original] == [
        (r["reviewed_at"], r["purchase_basis_id"]) for r in after
    ]
    world["allocations"].cancel(int(found[0].id), CancelBody(reason="撤回原票分配"), USER)
    assert Decimal(str(active_lines(engine)[0]["received_amount"])) == 0
    assert task(engine)["status"] == "partially_received"


def test_invoice_version_retains_occupancy_and_original_confirmation(engine, world, reviewed):
    target, found = confirm_all(engine, world)
    original = rows(engine, "SELECT * FROM matching_allocations WHERE id=:id", id=int(found[0].id))[0]
    import_invoices(world, [invoice("26000000000000008801", [INK, FLUID], remark="SUB-200 补充说明")])
    assert all(r["requires_review"] for r in active_lines(engine))
    assert len(rows(engine, "SELECT id FROM invoice_versions")) == 2
    current = world["queries"].invoice(target)
    row = current.items[0].allocations[0]
    assert row.verificationStatus == "needs_review" and row.reverify.allowed
    assert row.statusLabel == "已确认 · 待复核"
    world["allocations"].reverify(int(found[0].id), ConfirmBody(note="已核实新版本仅改备注"), USER)
    saved = rows(engine, "SELECT * FROM matching_allocations WHERE id=:id", id=int(found[0].id))[0]
    assert saved["reviewed_at"] == original["reviewed_at"]
    assert saved["invoice_version_id"] == original["invoice_version_id"]
    assert saved["verification_status"] == "valid"
    assert json.loads(saved["verification_history"])[-1]["note"] == "已核实新版本仅改备注"


def test_void_invoice_reopens_completed_without_releasing_capacity(engine, world, reviewed):
    target, found = confirm_all(engine, world)
    import_invoices(world, [invoice("26000000000000008801", [INK, FLUID], remark="SUB-200", status="作废")])
    assert task(engine)["status"] != "completed"
    assert all(
        r["verification_status"] == "invalid" and r["status"] == "confirmed"
        for r in rows(engine, "SELECT * FROM matching_allocations")
    )
    with pytest.raises(ApiError, match="作废"):
        world["allocations"].reverify(int(found[0].id), ConfirmBody(note="不能绕过作废"), USER)


def test_reordering_preserves_logical_identity_and_duplicate_items_block(engine, world, reviewed):
    target, _ = confirm_all(engine, world)
    before = rows(engine, "SELECT id,item_name FROM invoice_items ORDER BY id")
    result = import_invoices(world, [invoice("26000000000000008801", [FLUID, INK], remark="SUB-200")])
    assert result.unchanged == 1
    assert rows(engine, "SELECT id,item_name FROM invoice_items ORDER BY id") == before
    import_invoices(world, [invoice("26000000000000008801", [INK, INK], remark="SUB-200")])
    assert rows(engine, "SELECT detail_status FROM invoice_headers")[0]["detail_status"] == "failed"
    assert rows(engine, "SELECT id,item_name FROM invoice_items ORDER BY id") == before
    assert all(r["requires_review"] for r in active_lines(engine))


def test_unit_conversion_exactness_and_difference_closure_revoked(engine, world, reviewed):
    number = "26000000000000008802"
    import_invoices(world, [invoice(number, [("墨水", "箱", "1", "88.94", "11.56")], remark="SUB-200")])
    target = invoice_id(engine, number)
    # 单位不同不自动建议，人工关联时仍可经接口提交换算因子
    assert proposals(world, target) == []
    item = world["queries"].invoice(target).items[0]
    line_id = rows(engine, "SELECT id FROM source_purchase_order_lines ORDER BY id")[0]["id"]
    body = ManualBody(
        requestId=uuid4(),
        invoiceId=str(target),
        invoiceItemId=item.id,
        purchaseLineId=str(line_id),
        quantity="1",
        amount="100.50",
        note="确认",
        conversionDenominator="3",
    )
    with pytest.raises(ApiError, match="8 位小数"):
        world["allocations"].create_manual(body, USER)
    world["allocations"].create_manual(
        body.model_copy(
            update={
                "requestId": uuid4(),
                "note": "一箱十二个",
                "conversionNumerator": Decimal(12),
                "conversionDenominator": Decimal(1),
            }
        ),
        USER,
    )
    row = world["queries"].invoice(target).items[0].allocations[0]
    line = active_lines(engine)[0]
    assert Decimal(str(line["received_quantity"])) == 12 and line["status"] == "partial"
    service = ClosureService(engine, world["tasks"])
    body = ClosureRequest(
        requestId=uuid4(),
        purchaseBasisId=str(line["purchase_basis_id"]),
        ledgerSha256=line["ledger_sha256"],
        reason="多开两件不再补退",
    )
    service.close(line["task_id"], line["id"], body, USER)
    service.close(line["task_id"], line["id"], body, USER)
    assert active_lines(engine)[0]["closed_with_difference"]
    assert len(rows(engine, "SELECT id FROM task_events WHERE event_type='difference_closed'")) == 1
    world["allocations"].cancel(int(row.id), CancelBody(reason="撤回"), USER)
    assert not active_lines(engine)[0]["closed_with_difference"]
    assert active_lines(engine)[0]["closure_event_id"] is None
    with pytest.raises(ApiError, match="已变化"):
        service.close(line["task_id"], line["id"], body.model_copy(update={"requestId": uuid4()}), USER)


def test_replacement_failure_rolls_back_original_and_retry_is_idempotent(engine, world, reviewed):
    complete_documents(engine)  # 完结需资料齐全；本测试关注收票与账本
    target, found = confirm_all(engine, world)
    old = found[0]
    body = ReplaceBody(
        requestId=uuid4(),
        invoiceId=str(target),
        invoiceItemId=old.invoiceItemId,
        purchaseLineId=old.purchase.purchaseLineId,
        quantity="11",
        amount="100.50",
        note="更正分配",
        reason="原记录更正",
    )
    with pytest.raises(ApiError, match="超过发票行"):
        world["allocations"].replace(int(old.id), body, USER)
    assert (
        rows(engine, "SELECT status FROM matching_allocations WHERE id=:id", id=int(old.id))[0]["status"]
        == "confirmed"
    )
    body = body.model_copy(update={"quantity": Decimal("10")})
    world["allocations"].replace(int(old.id), body, USER)
    world["allocations"].replace(int(old.id), body, USER)
    assert (
        len(rows(engine, "SELECT id FROM matching_allocations WHERE request_id=:id", id=str(body.requestId)))
        == 1
    )
    assert task(engine)["status"] == "completed"


def test_manual_currency_evidence_and_parent_change_fanout(ns, engine, world):
    parent = {**PARENT, "currencysymbol": "", "currencyname": "未识别"}
    save(
        ns,
        engine,
        bundle(
            [purchase(), purchase("201", "871")], [customs("870"), customs("871")], parents={"100": parent}
        ),
    )
    item = world["review"].browse(DeclarationListQuery()).groups[0]
    order = rows(engine, "SELECT id FROM source_purchase_orders WHERE ns_internal_id='201'")[0]
    body = ApproveRequest(
        contentSha256=item.contentSha256,
        currencyEvidence=[
            {
                "purchaseOrderId": str(order["id"]),
                "currency": "CNY",
                "reference": "合同币种页",
                "note": "供应商原件核实",
            }
        ],
    )
    # 精确选择这张报关单，避免依赖列表排序。
    item = next(g for g in world["review"].browse(DeclarationListQuery()).groups if g.recordNumber == "CD871")
    body = body.model_copy(update={"contentSha256": item.contentSha256})
    world["review"].approve(int(item.id), body, USER)
    frozen = rows(engine, "SELECT * FROM review_purchase_bases WHERE currency_source='manual_verified'")
    assert len(frozen) == 2 and all(r["currency"] == "CNY" for r in frozen)
    shown = next(
        g for g in world["review"].browse(DeclarationListQuery()).groups if g.recordNumber == "CD871"
    )
    assert any("合同币种页" in text for text in shown.currencyEvidenceSummary)
    # 只同步兄弟单，母单币种变更仍使未出现的 201 单失效。
    save(
        ns,
        engine,
        bundle(
            [purchase()],
            [customs("870")],
            parents={"100": {**PARENT, "currencysymbol": "USD", "currencyname": "美元"}},
        ),
    )
    assert all(r["status"] == "review_required" for r in rows(engine, "SELECT * FROM review_purchase_bases"))
    assert all(r["requires_review"] for r in active_lines(engine))


def test_subscriber_failure_rolls_back_invoice_version_and_progress(engine, world, reviewed, monkeypatch):
    complete_documents(engine)  # 完结需资料齐全；本测试关注收票与账本
    confirm_all(engine, world)
    from backend.modules.task.service import progress_service

    def fail(*args):
        raise SQLAlchemyError("isolated failure")

    monkeypatch.setattr(progress_service, "apply_receipt", fail)
    with pytest.raises(ApiError):
        import_invoices(world, [invoice("26000000000000008801", [INK, FLUID], remark="SUB-200 changed")])
    assert len(rows(engine, "SELECT id FROM invoice_versions")) == 1
    assert task(engine)["status"] == "completed"
    assert all(
        r["verification_status"] == "valid" for r in rows(engine, "SELECT * FROM matching_allocations")
    )


def test_rebuild_after_restart_uses_ledger_not_task_cache(engine, world, reviewed):
    complete_documents(engine)  # 完结需资料齐全；本测试关注收票与账本
    from backend.app import create_events
    from backend.modules.matching.service.rebuild_service import rebuild

    confirm_all(engine, world)
    with engine.begin() as c:
        c.exec_driver_sql("UPDATE task_lines SET received_quantity=0,received_amount=0,status='open'")
        c.exec_driver_sql("UPDATE task_tasks SET status='documents_pending'")
    rebuild(engine, create_events())
    first = active_lines(engine)
    rebuild(engine, create_events())
    assert [{k: v for k, v in row.items() if k != "updated_at"} for row in active_lines(engine)] == [
        {k: v for k, v in row.items() if k != "updated_at"} for row in first
    ]
    assert task(engine)["status"] == "completed"


def test_same_purchase_on_second_declaration_does_not_duplicate_quota(ns, engine, world, reviewed):
    before = active_lines(engine)
    save(ns, engine, bundle([purchase(customs_id="871")], [customs("871")]))
    approve(world, "CD871")
    assert len(rows(engine, "SELECT id FROM task_tasks")) == 1
    assert [r["id"] for r in active_lines(engine)] == [r["id"] for r in before]
    assert len(rows(engine, "SELECT id FROM review_purchase_bases")) == 2
    assert rows(engine, "SELECT id FROM task_events WHERE event_type='evidence_linked'")


def test_replace_completed_line_is_selectable_without_false_overage(engine, world, reviewed):
    complete_documents(engine)  # 完结需资料齐全；本测试关注收票与账本
    target, found = confirm_all(engine, world)
    old = found[0]
    candidates = world["queries"].candidates(
        CandidateQuery(invoiceId=str(target), invoiceItemId=old.invoiceItemId)
    )
    assert any(row.purchase.purchaseLineId == old.purchaseLineId for row in candidates.rows)
    body = ReplaceBody(
        requestId=uuid4(),
        invoiceId=str(target),
        invoiceItemId=old.invoiceItemId,
        purchaseLineId=old.purchaseLineId,
        quantity=old.quantity,
        amount=old.amount,
        note="隔离测试核实原分配",
        reason="同一采购行重新确认凭据",
    )
    world["allocations"].replace(int(old.id), body, USER)
    current = rows(engine, "SELECT * FROM matching_allocations WHERE request_id=:id", id=str(body.requestId))[
        0
    ]
    assert not current["exceeds_expected"]
    assert task(engine)["status"] == "completed"
