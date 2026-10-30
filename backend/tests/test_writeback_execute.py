"""NS 写入链路：使用隔离库与伪造写入接口，不触发真实 NS 写入。"""

import time
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.integrations.netsuite.client import NetSuite, WriteOutcomeUnknown
from backend.modules.matching.dto.matching_dto import CancelBody
from backend.modules.writeback.dao import lock_dao, task_dao
from backend.modules.writeback.dto.task_dto import ConfirmPreview, ResolveWrite
from backend.modules.writeback.entity import requests, target_locks
from backend.modules.writeback.policy.write_gate import WriteGate
from backend.modules.writeback.service.execute_service import ExecuteService
from backend.modules.writeback.service.queue_service import now
from backend.modules.writeback.service.task_service import TaskService
from backend.tests.test_matching import USER
from backend.tests.test_writeback_prepare import confirmation, query, result
from backend.tests.test_writeback_prepare import engine as engine
from backend.tests.test_writeback_prepare import ns as ns
from backend.tests.test_writeback_prepare import prepared as prepared
from backend.tests.test_writeback_prepare import world as world
from sqlalchemy import select

OPEN = SimpleNamespace(
    write_enabled=True, vendor_bill_writeback_script="9", writeback_vendor_allowlist=("77",)
)


class Gateway:
    def __init__(self, respond):
        self.respond, self.calls = respond, []

    def vendor_bill_writeback(self, payload):
        self.calls.append(deepcopy(payload))
        return self.respond(payload)


def response(payload, status="APPLIED", **changes):
    body = {
        "contractVersion": 1,
        "source": "vendor-bill-writeback",
        "account": "prod",
        "complete": True,
        "requestId": payload["requestId"],
        "status": status,
        "written": status in ("APPLIED", "PARTIAL"),
    }
    if body["written"]:
        body["invoiceRecordId"] = "7001"
        body["bills"] = [
            {
                "billId": line["billId"],
                "billNumber": "TEST-BILL",
                "status": "UPDATED",
                "before": line["expectedBefore"],
                "amount": line["amount"],
                "after": line["amount"],
                "verified": status == "APPLIED",
            }
            for line in payload["bills"]
        ]
    return {**body, **changes}


def setup(prepared, respond=response, settings=OPEN, payload=None):
    task = query(prepared, payload)
    prepared.service.confirm(prepared.task_id, confirmation(task), USER)
    tasks = TaskService(prepared.service.engine, "prod", gate=WriteGate(settings))
    gateway = Gateway(respond)
    return tasks, ExecuteService(tasks, gateway), gateway


def execute(tasks, executor, prepared):
    return executor.execute(prepared.task_id, tasks.get(prepared.task_id)["revision"], USER)


def locks(engine):
    with engine.connect() as connection:
        return [row.bill_id for row in connection.execute(select(target_locks))]


def test_query_detected_registration_blocks_even_direct_execute(prepared):
    tasks, executor, gateway = setup(prepared)
    payload = result()
    number = tasks.get(prepared.task_id)["invoiceNo"]
    payload["registrationCheck"] = {
        "invoiceNumber": number,
        "records": [{"id": "7001", "number": number, "date": "2026-10-30"}],
    }
    checked = query(prepared, payload)
    assert checked["state"] == "conflict" and checked["plan"] is None
    with pytest.raises(ApiError, match="任务不是待写入状态"):
        execute(tasks, executor, prepared)
    assert not gateway.calls and not locks(tasks.engine)


def test_legacy_ready_task_requires_registration_check_before_any_ns_write(prepared):
    tasks, executor, gateway = setup(prepared)
    with tasks.engine.begin() as connection:
        current = task_dao.get(connection, prepared.task_id)
        candidates = deepcopy(current["candidates"])
        candidates.pop("registrationCheck")
        task_dao.change(connection, prepared.task_id, {"candidates": candidates}, now())
    assert not tasks.get(prepared.task_id)["writeback"]["allowed"]
    with pytest.raises(ApiError, match="尚未完成本张发票的同号登记核对"):
        execute(tasks, executor, prepared)
    assert not gateway.calls and not locks(tasks.engine)


def test_execution_uses_current_connection_for_result_and_target_lock(prepared):
    tasks, _, _ = setup(prepared)
    current = TaskService(tasks.engine, "other", gate=WriteGate(OPEN))

    def respond(payload):
        with tasks.engine.connect() as connection:
            held = list(connection.execute(select(target_locks)).mappings())
        assert held and {row["ns_account"] for row in held} == {"other"}
        return response(payload, account="other")

    gateway = Gateway(respond)
    result = execute(current, ExecuteService(current, gateway), prepared)
    assert result["state"] == "applied"
    assert len(gateway.calls) == 1 and not locks(tasks.engine)


def test_second_execute_is_rejected_while_gateway_is_running(prepared):
    tasks, executor, gateway = setup(prepared)
    revision = tasks.get(prepared.task_id)["revision"]

    def slow_response(payload):
        running = tasks.get(prepared.task_id)
        assert running["state"] == "executing" and not running["actions"]["execute"]
        with pytest.raises(ApiError) as error:
            executor.execute(prepared.task_id, revision, USER)
        assert error.value.status == 409
        return response(payload)

    gateway.respond = slow_response
    assert executor.execute(prepared.task_id, revision, USER)["state"] == "applied"
    assert len(gateway.calls) == 1


def test_applied_freezes_payload_and_records_ns_result(engine, prepared):
    tasks, executor, gateway = setup(prepared)
    task = tasks.get(prepared.task_id)
    assert task["state"] == "ready" and task["actions"]["execute"]
    preview = task["request"]["preview"]
    assert [(line["before"], line["after"], line["consistent"]) for line in preview] == [
        ("0.00", task["amount"], True)
    ]
    done = execute(tasks, executor, prepared)
    assert done["state"] == "applied" and done["request"]["nsRecordId"] == "7001"
    [payload] = gateway.calls
    assert payload["action"] == "apply" and payload["vendorId"] == "77"
    assert payload["invoice"] == {
        "number": "26000000000000008999",
        "date": payload["invoice"]["date"],
        "amount": task["amount"],
    }
    assert payload["bills"] == [
        {"billId": "395762", "purchaseOrderId": "100", "amount": task["amount"], "expectedBefore": "0.00"}
    ]
    assert locks(engine) == []
    assert {"write_started", "write_finished"} <= {item["action"] for item in done["audit"]}
    assert not done["actions"]["execute"] and not done["actions"]["refresh"]
    # 写入后审核变化：保留已登记状态，只提示人工核对。
    prepared.world["allocations"].cancel(prepared.allocation_ids[0], CancelBody(reason="写入后撤销"), USER)
    after = tasks.get(prepared.task_id)
    assert after["state"] == "applied" and "写入 NS 后已变化" in after["reason"]


@pytest.mark.parametrize(
    "settings, reason",
    [
        (SimpleNamespace(**{**vars(OPEN), "write_enabled": False}), "写入开关"),
        (SimpleNamespace(**{**vars(OPEN), "vendor_bill_writeback_script": ""}), "尚未配置"),
        (SimpleNamespace(**{**vars(OPEN), "writeback_vendor_allowlist": ("88",)}), "白名单"),
        (SimpleNamespace(**{**vars(OPEN), "writeback_vendor_allowlist": ()}), "白名单"),
    ],
)
def test_gate_keeps_task_waiting_without_calling_ns(prepared, settings, reason):
    tasks, executor, gateway = setup(prepared, settings=settings)
    task = tasks.get(prepared.task_id)
    assert task["state"] == "ready" and not task["actions"]["execute"]
    assert reason in task["writeback"]["reason"]
    with pytest.raises(ApiError, match=reason):
        execute(tasks, executor, prepared)
    assert gateway.calls == []


def test_inconsistent_bill_requires_preview_confirmation(prepared):
    payload = result()
    bill = payload["purchaseOrders"][0]["bills"][0]
    bill["amounts"].update(received="30.00", available="970.00")
    bill.update(details={"count": 1, "total": "20.00"}, consistent=False)
    tasks, executor, gateway = setup(prepared, payload=payload)
    task = tasks.get(prepared.task_id)
    assert task["state"] == "needs_preview" and task["actions"]["confirmPreview"]
    [line] = task["request"]["preview"]
    assert (line["before"], line["after"], line["detailsTotal"], line["difference"]) == (
        "30.00",
        format(Decimal(task["amount"]) + 30, ".2f"),
        "20.00",
        "10.00",
    )
    with pytest.raises(ApiError):
        execute(tasks, executor, prepared)
    confirmed = executor.confirm_preview(
        prepared.task_id, ConfirmPreview(revision=task["revision"], confirmScope=True), USER
    )
    assert confirmed["state"] == "ready" and confirmed["request"]["confirmedBy"] == USER
    assert execute(tasks, executor, prepared)["state"] == "applied"
    assert gateway.calls[0]["bills"][0]["expectedBefore"] == "30.00"


def test_unknown_keeps_lock_and_only_allows_manual_resolution(engine, prepared):
    def lost(payload):
        raise WriteOutcomeUnknown("ReadTimeout")

    tasks, executor, gateway = setup(prepared, respond=lost)
    task = execute(tasks, executor, prepared)
    assert task["state"] == "unknown" and task["actions"]["resolve"] and task["actions"]["markNotWritten"]
    assert locks(engine) == ["395762"]
    with pytest.raises(ApiError):
        execute(tasks, executor, prepared)
    with pytest.raises(ApiError, match="不能重新查询"):
        query(prepared)
    retried = executor.resolve(
        prepared.task_id,
        ResolveWrite(revision=task["revision"], outcome="not_written", evidence="已在 NS 按发票号核实无登记"),
        USER,
    )
    assert retried["state"] == "ready" and locks(engine) == []
    gateway.respond = response
    assert execute(tasks, executor, prepared)["state"] == "applied"
    assert len(gateway.calls) == 2 and gateway.calls[0]["requestId"] == gateway.calls[1]["requestId"]


def test_partial_cannot_be_marked_not_written(engine, prepared):
    tasks, executor, _ = setup(prepared, respond=lambda payload: response(payload, "PARTIAL"))
    task = execute(tasks, executor, prepared)
    assert task["state"] == "partial" and not task["actions"]["markNotWritten"]
    assert task["request"]["nsRecordId"] == "7001" and locks(engine) == ["395762"]
    with pytest.raises(ApiError, match="不能标记为未写入"):
        executor.resolve(
            prepared.task_id,
            ResolveWrite(revision=task["revision"], outcome="not_written", evidence="已在 NS 核实记录存在"),
            USER,
        )
    done = executor.resolve(
        prepared.task_id,
        ResolveWrite(
            revision=task["revision"], outcome="applied", evidence="已在 NS 补齐账单累计", nsRecordId="7001"
        ),
        USER,
    )
    assert done["state"] == "applied" and locks(engine) == []


@pytest.mark.parametrize(
    "respond, state, reason",
    [
        (
            lambda p: response(p, "CONFLICT", existing=[{"id": "51601", "number": "x", "date": "2026/3/20"}]),
            "conflict",
            "51601",
        ),
        (
            lambda p: response(p, "REJECTED", problems=[{"billId": "395762", "code": "STALE"}]),
            "blocked",
            "重新查询账单",
        ),
        (
            lambda p: {
                **response(p),
                "complete": False,
                "error": {"code": "WRITE_FAILED"},
                "status": None,
                "written": False,
            },
            "blocked",
            "未写入",
        ),
    ],
)
def test_nothing_written_outcomes_release_locks(engine, prepared, respond, state, reason):
    tasks, executor, _ = setup(prepared, respond=respond)
    task = execute(tasks, executor, prepared)
    assert task["state"] == state and reason in task["reason"]
    assert locks(engine) == []
    assert task["actions"]["refresh"]


@pytest.mark.parametrize(
    "change",
    [
        {"requestId": str(uuid4())},
        {"account": "other"},
        {"contractVersion": 2},
        {"bills": []},
        {"invoiceRecordId": None},
    ],
)
def test_unverifiable_response_is_unknown(engine, prepared, change):
    tasks, executor, _ = setup(prepared, respond=lambda payload: {**response(payload), **change})
    assert execute(tasks, executor, prepared)["state"] == "unknown"
    assert locks(engine) == ["395762"]


def test_request_not_sent_returns_to_ready(engine, prepared):
    def refused(payload):
        raise ApiError(502, "NS 连接失败，写入请求未发出")

    tasks, executor, _ = setup(prepared, respond=refused)
    task = execute(tasks, executor, prepared)
    assert task["state"] == "ready" and "未发出" in task["reason"]
    assert locks(engine) == []
    with engine.connect() as connection:
        assert connection.execute(select(requests.c.state)).scalar_one() == "pending"


def test_bill_locked_by_other_request_blocks_execution(engine, prepared):
    tasks, executor, gateway = setup(prepared)
    with engine.connect() as connection:
        request_id = connection.execute(select(requests.c.id)).scalar_one()
    with transaction(engine) as connection:
        lock_dao.acquire(connection, "prod", ["395762"], request_id, now())
    with pytest.raises(ApiError, match="占用"):
        execute(tasks, executor, prepared)
    assert gateway.calls == []


def client_for(handler, **changes):
    settings = Settings(
        account="test-sb1",
        scope=["restlets"],
        write_enabled=True,
        vendor_bill_writeback_script="501",
        vendor_bill_writeback_deploy="1",
    )
    for key, value in changes.items():
        setattr(settings, key, value)
    ns = NetSuite(settings, httpx.Client(transport=httpx.MockTransport(handler)))
    ns._cached = ("private-token", time.monotonic() + 300)
    return ns


def test_client_separates_not_sent_from_unknown():
    calls = []

    def ok(request):
        calls.append(request)
        return httpx.Response(200, json={"status": "APPLIED"})

    ns = client_for(ok)
    assert ns.vendor_bill_writeback({"action": "apply"}) == {"status": "APPLIED"}
    assert calls[0].url.params["script"] == "501" and calls[0].url.params["deploy"] == "1"

    def raises(error):
        def handle(request):
            raise error("boom", request=request)

        return handle

    for handler, expected in [
        (raises(httpx.ConnectError), ApiError),
        (raises(httpx.ReadTimeout), WriteOutcomeUnknown),
        (lambda _: httpx.Response(401), ApiError),
        (lambda _: httpx.Response(403), ApiError),
        (lambda _: httpx.Response(500), WriteOutcomeUnknown),
        (lambda _: httpx.Response(400, json={"error": "script"}), WriteOutcomeUnknown),
        (lambda _: httpx.Response(200, content=b"not json"), WriteOutcomeUnknown),
    ]:
        with pytest.raises(expected):
            client_for(handler).vendor_bill_writeback({"action": "apply"})

    # 开关关闭或未配置时请求不发出。
    for changes in ({"write_enabled": False}, {"vendor_bill_writeback_script": ""}):
        sent = []
        with pytest.raises(ApiError):
            client_for(lambda request: sent.append(request), **changes).vendor_bill_writeback({})
        assert sent == []


def test_old_split_plan_cannot_execute_and_remains_auditable(engine, prepared):
    from backend.modules.writeback.entity import plans
    from sqlalchemy import update

    tasks, executor, gateway = setup(prepared)
    with engine.begin() as connection:
        plan = dict(connection.execute(select(plans)).mappings().one())
        old_body = deepcopy(plan["body"])
        old_body["allocations"][1]["billId"] = "395763"
        connection.execute(update(plans).where(plans.c.id == plan["id"]).values(body=old_body))
    detail = tasks.get(prepared.task_id)
    assert not detail["actions"]["execute"]
    assert "重新查询账单" in detail["reason"]
    assert len(detail["plan"]["orders"]) == 2
    with pytest.raises(ApiError, match="同一子采购单"):
        executor.execute(prepared.task_id, detail["revision"], USER)
    assert not gateway.calls
    assert locks(engine) == []
    with engine.connect() as connection:
        assert connection.execute(select(plans.c.body)).scalar_one() == old_body
