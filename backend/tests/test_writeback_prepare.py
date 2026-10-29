"""准备链路使用隔离库与合成来源；不触发真实 NS 写入。"""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.modules.matching.dto.matching_dto import CancelBody, ConfirmBody
from backend.modules.source.service.vendor_bill_query_service import VendorBillQueryService
from backend.modules.writeback.dao import task_dao
from backend.modules.writeback.dto.task_dto import ConfirmPlan, TaskQuery
from backend.modules.writeback.entity import plans, tasks
from backend.modules.writeback.service.query_service import QueryService
from backend.modules.writeback.service.queue_service import enqueue
from backend.modules.writeback.service.task_service import TaskService
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, USER, approve, import_invoices, invoice_id, proposals
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from sqlalchemy import select, text


@pytest.fixture
def prepared(engine, ns, world):
    save(ns, engine, bundle([purchase()], [customs()]))
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE source_parent_orders SET currency_internal_id='1', supplier_id=(SELECT id FROM source_suppliers LIMIT 1)"
            )
        )
    approve(world, "CD870")
    import_invoices(world, [invoice("26000000000000008999", [INK, FLUID], remark="SUB-200")])
    target = invoice_id(engine, "26000000000000008999")
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE invoice_headers SET buyer_name='采购公司A', buyer_name_normalized='采购公司a' WHERE id=:id"
            ),
            {"id": target},
        )
    found = proposals(world, target)
    for proposal in found:
        world["allocations"].confirm(int(proposal.id), ConfirmBody(), USER)
    service = TaskService(engine, "prod")
    ready = service.invoice(target)
    assert ready["ready"], ready
    task_id = int(ready["task"]["id"])
    return SimpleNamespace(
        service=service,
        task_id=task_id,
        invoice_id=target,
        world=world,
        allocation_ids=[int(p.id) for p in found],
    )


def result():
    bill = {
        "billId": "395762",
        "billNumber": "TEST-BILL",
        "vendorId": "77",
        "purchaseOrderId": "100",
        "subPurchaseOrderId": "",
        "subsidiaryId": "1",
        "currencyId": "1",
        "currencyName": "人民币",
        "approvalStatus": "2",
        "voided": False,
        "hasTax": True,
        "amounts": {
            "remaining": "1000.00",
            "applied": "0.00",
            "payable": "1000.00",
            "received": "0.00",
            "available": "1000.00",
        },
        "details": {"count": 0, "total": "0.00"},
        "consistent": True,
    }
    return {
        "contractVersion": 3,
        "complete": True,
        "source": "vendor-bill-query",
        "account": "prod",
        "query": {"vendorId": "77", "purchaseOrderIds": ["100"]},
        "readStartedAt": "2026-10-28T00:00:00Z",
        "readCompletedAt": "2026-10-28T00:00:01Z",
        "status": "OK",
        "vendor": {"id": "77", "code": "TEST", "name": "合成供应商"},
        "purchaseOrders": [
            {
                "id": "100",
                "number": "PO-100",
                "vendorId": "77",
                "subsidiaryId": "1",
                "currencyId": "1",
                "currencyName": "人民币",
                "status": "FOUND",
                "bills": [bill],
            }
        ],
    }


def query(prepared, payload=None, during=None):
    data = result() if payload is None else payload

    def call(criteria):
        assert criteria == {"vendorId": "77", "purchaseOrderIds": ["100"]}
        if during:
            during()
        return deepcopy(data)

    ns = SimpleNamespace(settings=SimpleNamespace(account="prod"), vendor_bill_query=call)
    service = QueryService(prepared.service, VendorBillQueryService(ns))
    current = prepared.service.get(prepared.task_id)
    return service.refresh(prepared.task_id, current["revision"], USER)


def confirmation(task):
    return ConfirmPlan(
        revision=task["revision"],
        requestId=uuid4(),
        confirmScope=True,
        evidence="已核实实际子公司 1 和母单结算归属，测试凭据 TEST-1",
        allocations=[
            {"allocationId": a["allocationId"], "billId": "395762", "amount": a["amount"]}
            for a in task["allocations"]
        ],
    )


def test_atomic_enqueue_and_idempotent_confirmation(engine, prepared):
    assert prepared.service.list(TaskQuery())["total"] == 1
    prepared.service.recheck(prepared.invoice_id, USER)
    assert prepared.service.list(TaskQuery())["total"] == 1
    task = query(prepared)
    assert task["state"] == "needs_confirmation"  # 唯一账单不能证明精确归属。
    body = confirmation(task)
    done = prepared.service.confirm(prepared.task_id, body, USER)
    assert done["state"] == "ready" and done["writeback"]["allowed"] is False
    prepared.service.confirm(prepared.task_id, body, USER)
    with engine.connect() as connection:
        assert len(connection.execute(select(plans)).all()) == 1
    with pytest.raises(ApiError, match="请求编号"):
        prepared.service.confirm(
            prepared.task_id, body.model_copy(update={"evidence": "不同内容不能复用请求"}), USER
        )


@pytest.mark.parametrize(
    "buyer, normalized, allowed",
    [(None, None, True), ("", "", True), ("采购公司A", "采购公司a", True), ("其他公司", "其他公司", False)],
)
def test_buyer_missing_or_matching_can_enqueue_but_mismatch_requires_review(
    engine, ns, world, buyer, normalized, allowed
):
    save(ns, engine, bundle([purchase()], [customs()]))
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE source_parent_orders SET currency_internal_id='1', supplier_id=(SELECT id FROM source_suppliers LIMIT 1)"
            )
        )
    approve(world, "CD870")
    import_invoices(world, [invoice("26000000000000008999", [INK, FLUID], remark="SUB-200")])
    target = invoice_id(engine, "26000000000000008999")
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE invoice_headers SET buyer_name=:buyer, buyer_name_normalized=:normalized WHERE id=:id"
            ),
            {"buyer": buyer, "normalized": normalized, "id": target},
        )
    for proposal in proposals(world, target):
        world["allocations"].confirm(int(proposal.id), ConfirmBody(note="已核实发票分配"), USER)
    service = TaskService(engine, "prod")
    readiness = service.invoice(target)
    assert readiness["ready"] is allowed
    assert service.list(TaskQuery())["total"] == int(allowed)
    if allowed:
        assert readiness["task"]["state"] == "queued"
        service.recheck(target, USER)
        assert service.list(TaskQuery())["total"] == 1
        with engine.connect() as connection:
            snapshot = task_dao.current(connection, target)["snapshot"]
        assert snapshot["invoice"]["buyer_name"] == buyer
    else:
        assert readiness["task"] is None
        assert readiness["reason"] == "票面购买方与采购公司身份待核实"
        assert service.recheck(target, USER)["task"] is None


def test_missing_buyer_does_not_bypass_parent_supplier_check(engine, prepared):
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE invoice_headers SET buyer_name=NULL, buyer_name_normalized=NULL WHERE id=:id"),
            {"id": prepared.invoice_id},
        )
        connection.execute(text("UPDATE source_parent_orders SET supplier_id=NULL"))
    readiness = prepared.service.invoice(prepared.invoice_id)
    assert not readiness["ready"]
    assert readiness["reason"] == "母采购或供应商关系尚待核实"
    assert prepared.service.get(prepared.task_id)["state"] == "stale"


def test_query_outside_transaction_and_cancel_discards_late_result(prepared):
    task = query(
        prepared,
        during=lambda: prepared.world["allocations"].cancel(
            prepared.allocation_ids[0], CancelBody(reason="取消测试"), USER
        ),
    )
    assert task["state"] == "stale" and task["candidates"] is None
    assert not task["actions"]["confirm"]


def test_cancel_invalidates_frozen_plan_but_preserves_evidence(prepared):
    task = query(prepared)
    prepared.service.confirm(prepared.task_id, confirmation(task), USER)
    prepared.world["allocations"].cancel(prepared.allocation_ids[0], CancelBody(reason="撤销分配"), USER)
    task = prepared.service.get(prepared.task_id)
    assert task["state"] == "stale" and task["plan"] is not None


def test_requery_invalidates_old_confirmation(prepared):
    old = query(prepared)
    query(prepared)
    with pytest.raises(ApiError, match="版本已变化"):
        prepared.service.confirm(prepared.task_id, confirmation(old), USER)


@pytest.mark.parametrize(
    "change",
    [
        "wrong_account",
        "wrong_vendor",
        "missing_order",
        "unapproved",
        "voided",
        "other_child",
        "currency",
        "over_capacity",
    ],
)
def test_bad_candidates_cannot_be_confirmed(prepared, change):
    payload = result()
    bill = payload["purchaseOrders"][0]["bills"][0]
    if change == "wrong_account":
        payload["account"] = "other"
    if change == "wrong_vendor":
        bill["vendorId"] = "88"
    if change == "missing_order":
        payload["purchaseOrders"] = []
    if change == "unapproved":
        bill["approvalStatus"] = "1"
    if change == "voided":
        bill["voided"] = True
    if change == "other_child":
        bill["subPurchaseOrderId"] = "999"
    if change == "currency":
        bill["currencyName"] = "美元"
    if change == "over_capacity":
        bill["amounts"].update(remaining="110.00", payable="110.00", available="110.00")
    task = query(prepared, payload)
    if task["state"] == "blocked":
        assert not task["actions"]["confirm"]
    else:
        with pytest.raises(ApiError):
            prepared.service.confirm(prepared.task_id, confirmation(task), USER)


def test_target_conservation_and_duplicate_pairs(prepared):
    task = query(prepared)
    body = confirmation(task)
    for targets in [
        body.allocations[:1],
        [body.allocations[0], *body.allocations],
        [body.allocations[0].model_copy(update={"amount": "100.49"}), body.allocations[1]],
    ]:
        with pytest.raises(ApiError):
            prepared.service.confirm(prepared.task_id, body.model_copy(update={"allocations": targets}), USER)


def test_service_identity_and_account_isolation(prepared):
    task = query(prepared)
    with pytest.raises(ApiError) as error:
        prepared.service.confirm(prepared.task_id, confirmation(task), "service:test")
    assert error.value.status == 403
    other = TaskService(prepared.service.engine, "other")
    assert other.list(TaskQuery())["total"] == 0
    with pytest.raises(ApiError) as error:
        other.get(prepared.task_id)
    assert error.value.status == 404


def test_queue_failure_rolls_back_matching_confirmation(engine, ns, world, monkeypatch):
    save(ns, engine, bundle([purchase()], [customs()]))
    approve(world, "CD870")
    import_invoices(world, [invoice("26000000000000008888", [INK], remark="SUB-200")])
    proposal = proposals(world, invoice_id(engine, "26000000000000008888"))[0]

    def fail(*args, **kwargs):
        raise RuntimeError("queue failure")

    monkeypatch.setattr("backend.modules.writeback.service.queue_service.enqueue", fail)
    with pytest.raises(RuntimeError, match="queue failure"):
        world["allocations"].confirm(int(proposal.id), ConfirmBody(), USER)
    assert (
        rows(engine, "SELECT status FROM matching_allocations WHERE id=:id", id=int(proposal.id))[0]["status"]
        == "proposed"
    )


def test_snapshot_is_immutable_and_readiness_detects_incomplete_amount(engine, prepared):
    with transaction(engine) as connection:
        before = task_dao.get(connection, prepared.task_id)["snapshot"]
        connection.execute(
            text("UPDATE matching_allocations SET amount=amount-0.01 WHERE id=:id"),
            {"id": prepared.allocation_ids[0]},
        )
        state = enqueue(connection, prepared.invoice_id, USER)
        assert not state["ready"] and "金额" in state["reason"]
    with engine.connect() as connection:
        after = connection.execute(select(tasks)).mappings().one()
        assert after["snapshot"] == before and after["state"] == "stale"


@pytest.mark.parametrize(
    "sql, reason",
    [
        ("UPDATE matching_allocations SET quantity=quantity-1 WHERE id=:id", "数量"),
        ("UPDATE matching_allocations SET verification_status='needs_review' WHERE id=:id", "复核"),
        ("UPDATE invoice_headers SET current_version_id=current_version_id+1 WHERE id=:id", "版本"),
        ("UPDATE invoice_headers SET status='void' WHERE id=:id", "正常"),
        ("UPDATE invoice_headers SET tax_amount=NULL WHERE id=:id", "税额不明"),
        ("UPDATE matching_allocations SET conversion_numerator=2 WHERE id=:id", "换算"),
    ],
)
def test_readiness_rejects_changed_versions_units_and_incomplete_invoice(engine, prepared, sql, reason):
    with engine.begin() as connection:
        connection.execute(
            text(sql), {"id": prepared.invoice_id if "invoice_headers" in sql else prepared.allocation_ids[0]}
        )
    readiness = prepared.service.invoice(prepared.invoice_id)
    assert not readiness["ready"] and reason in readiness["reason"]
    assert prepared.service.get(prepared.task_id)["state"] == "stale"


def test_zero_tax_invoice_and_bill_can_be_confirmed(engine, prepared):
    # 2026-10-28 确认：采购税额为 0 也须登记。
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE invoice_headers SET tax_amount=0 WHERE id=:id"), {"id": prepared.invoice_id}
        )
    assert prepared.service.invoice(prepared.invoice_id)["ready"]
    prepared.service.recheck(prepared.invoice_id, USER)
    payload = result()
    payload["purchaseOrders"][0]["bills"][0]["hasTax"] = False
    # 税额变化会改变审核快照，重新检查后以当前任务为准。
    current = prepared.service.invoice(prepared.invoice_id)["task"]
    task = query(SimpleNamespace(**{**vars(prepared), "task_id": current["id"]}), payload)
    done = prepared.service.confirm(task["id"], confirmation(task), USER)
    assert done["state"] == "ready"


def test_waiting_bill_and_query_failure_are_distinct(prepared):
    payload = result()
    payload["purchaseOrders"][0].update(status="NO_BILLS", bills=[])
    assert query(prepared, payload)["state"] == "waiting_bill"
    task = query(prepared, {"complete": False, "error": {"code": "QUERY_FAILED"}})
    assert task["state"] == "blocked" and task["candidates"] is None
    assert task["audit"][0]["action"] == "query_failed"


def test_automatic_only_with_exact_child_company_and_nonhistorical_snapshot(engine, prepared):
    from backend.modules.writeback.policy.plan_policy import automatic_targets

    query(prepared)
    with engine.connect() as connection:
        task = task_dao.get(connection, prepared.task_id)
    candidates = task["candidates"]
    assert automatic_targets(task, candidates) is None
    for source in task["snapshot"]["sources"].values():
        source["company_ns_id"] = "subsidiary:1"
    candidates["purchaseOrders"][0]["bills"][0]["subPurchaseOrderId"] = "200"
    assert len(automatic_targets(task, candidates)) == 2
    task["historical"] = True
    assert automatic_targets(task, candidates) is None


def test_splits_across_bills_preserve_each_approved_amount(prepared):
    payload = result()
    other = deepcopy(payload["purchaseOrders"][0]["bills"][0])
    other.update(billId="395763", billNumber="TEST-2")
    payload["purchaseOrders"][0]["bills"].append(other)
    task = query(prepared, payload)
    body = confirmation(task).model_dump(mode="json")
    first = body["allocations"][0]
    first["amount"] = "50.00"
    body["allocations"].append({**first, "billId": "395763", "amount": "50.50"})
    assert prepared.service.confirm(prepared.task_id, ConfirmPlan(**body), USER)["state"] == "ready"


def test_http_routes_require_identity_and_write_needs_switch(context):
    from backend.app import create_app
    from fastapi.testclient import TestClient

    app = create_app(context.settings, context.ns, context.engine)
    with TestClient(app) as client:
        assert client.get("/api/writeback/tasks").status_code == 401
        headers = {"Authorization": f"Bearer {context.settings.service_key}"}
        response = client.get("/api/writeback/tasks?page=1&pageSize=20", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 0
    paths = set(app.openapi()["paths"])
    assert "/api/writeback/tasks/{task_id}/confirm" in paths
    assert "/api/writeback/tasks/{task_id}/execute" in paths
    assert "/api/writeback/tasks/{task_id}/resolve" in paths
    # 没有通用 apply/重发入口；执行只针对已冻结请求，开关关闭时后台不写入。
    assert not any(path.startswith("/api/writeback") and "apply" in path for path in paths)
    assert app.state.writeback_prepare_worker.executor is None
