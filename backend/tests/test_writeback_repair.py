"""账单补写（2026-11-10）：部分写入后只补写账单，不新建 NS 发票记录；使用隔离库与伪造写入接口。"""

from types import SimpleNamespace

import pytest
from backend.core.errors import ApiError
from backend.integrations.netsuite.client import WriteOutcomeUnknown
from backend.modules.writeback.policy.write_gate import WriteGate
from backend.modules.writeback.service.repair_service import RepairService
from backend.tests.test_matching import USER
from backend.tests.test_writeback_execute import OPEN, Gateway, execute, locks, response, setup
from backend.tests.test_writeback_prepare import engine as engine
from backend.tests.test_writeback_prepare import ns as ns
from backend.tests.test_writeback_prepare import prepared as prepared
from backend.tests.test_writeback_prepare import world as world


def repaired(payload, status="APPLIED", bill_status="UPDATED", **changes):
    body = response(payload, status, action="repair", **changes)
    for item in body.get("bills", []):
        item["status"] = bill_status
    return body


def partial_task(prepared):
    """模拟 NS 权限不足：发票记录 7001 已建、账单未更新。"""
    tasks, executor, _ = setup(prepared, respond=lambda payload: response(payload, "PARTIAL"))
    task = execute(tasks, executor, prepared)
    assert task["state"] == "partial" and task["actions"]["repair"] and locks(tasks.engine)
    return tasks


def run(tasks, prepared, respond):
    gateway = Gateway(respond)
    service = RepairService(tasks, gateway)
    task = service.repair(prepared.task_id, tasks.get(prepared.task_id)["revision"], USER)
    return task, gateway


def test_repair_reuses_record_and_releases_locks_when_all_bills_updated(prepared):
    tasks = partial_task(prepared)
    task, gateway = run(tasks, prepared, repaired)
    [sent] = gateway.calls
    assert sent["action"] == "repair" and sent["invoiceRecordId"] == "7001"
    assert task["state"] == "applied" and "已补写" in task["reason"]
    assert task["request"]["nsRecordId"] == "7001" and not locks(tasks.engine)
    actions = [row["action"] for row in task["audit"]]
    assert "repair_started" in actions and "repair_finished" in actions
    assert not task["actions"]["repair"] and not task["actions"]["resolve"]


def test_already_updated_bills_count_as_done(prepared):
    tasks = partial_task(prepared)
    task, _ = run(tasks, prepared, lambda payload: repaired(payload, bill_status="ALREADY_UPDATED"))
    assert task["state"] == "applied"


@pytest.mark.parametrize(
    ("respond", "state", "reason"),
    [
        # 再次补写仍失败（如权限未开通）：保持部分写入，锁不释放，可处理后再补写
        (lambda payload: repaired(payload, "PARTIAL"), "partial", "账单补写未全部完成"),
        # NS 复核不通过、旧版脚本拒绝正文：未改动账单，回到部分写入
        (
            lambda payload: repaired(
                payload, "REJECTED", written=False, problems=[{"billId": "", "code": "DETAIL_MISMATCH"}]
            ),
            "partial",
            "明细的账单或金额与本次回写不一致",
        ),
        (
            lambda payload: {
                **response(payload, "REJECTED"),
                "complete": False,
                "error": {"code": "INVALID_REQUEST"},
            },
            "partial",
            "尚未更新到支持账单补写的版本",
        ),
        # 返回的发票记录与本任务不一致：结果不明，须人工核实
        (lambda payload: repaired(payload, invoiceRecordId="7999"), "unknown", "发票记录与本任务不一致"),
    ],
)
def test_repair_outcomes_keep_locks_until_complete(prepared, respond, state, reason):
    tasks = partial_task(prepared)
    task, _ = run(tasks, prepared, respond)
    assert task["state"] == state and reason in task["reason"]
    assert locks(tasks.engine)
    assert task["actions"]["repair"] is (state == "partial")


def test_lost_response_becomes_unknown_without_retry(prepared):
    tasks = partial_task(prepared)

    def lost(payload):
        raise WriteOutcomeUnknown("timeout")

    task, gateway = run(tasks, prepared, lost)
    assert task["state"] == "unknown" and len(gateway.calls) == 1 and locks(tasks.engine)


def test_repair_only_for_partial_tasks_with_record_and_open_gate(prepared):
    tasks, executor, _ = setup(prepared)
    service = RepairService(tasks, Gateway(repaired))
    with pytest.raises(ApiError, match="只有部分写入"):
        service.repair(prepared.task_id, tasks.get(prepared.task_id)["revision"], USER)
    partial = partial_task(prepared)
    closed = type(partial)(
        partial.engine, "prod", gate=WriteGate(SimpleNamespace(**{**vars(OPEN), "write_enabled": False}))
    )
    blocked = RepairService(closed, Gateway(repaired))
    with pytest.raises(ApiError, match="写入开关未开启"):
        blocked.repair(prepared.task_id, closed.get(prepared.task_id)["revision"], USER)
    assert not closed.get(prepared.task_id)["repair"]["allowed"]
    with pytest.raises(ApiError, match="服务身份只读"):
        RepairService(partial, Gateway(repaired)).repair(
            prepared.task_id, partial.get(prepared.task_id)["revision"], "service:sync"
        )
    with pytest.raises(ApiError, match="任务已变化"):
        RepairService(partial, Gateway(repaired)).repair(prepared.task_id, 1, USER)
    assert partial.get(prepared.task_id)["state"] == "partial"
