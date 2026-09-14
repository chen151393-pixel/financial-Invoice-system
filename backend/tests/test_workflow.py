from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from backend.database import audit, previews, target_locks
from backend.netsuite import ApiError
from backend.workflow import Workflow, millis
from sqlalchemy import func, select, update

UPDATE = {"operation": "update", "type": "vendorBill", "id": "1", "payload": {"memo": "已校对"}}


def test_preview_read_only_immutable_and_execute_once(context):
    c = context
    p = c.workflow.preview(UPDATE, "user:admin")
    assert p["before"]["memo"] == "old" and not c.ns.writes
    p["payload"]["memo"] = "tampered"
    result = c.workflow.execute(p["id"], "user:admin")
    assert result["state"] == "succeeded"
    assert c.ns.writes[0][3] == {"memo": "已校对"}
    c.workflow.execute(p["id"], "user:admin")
    assert len(c.ns.writes) == 1
    with c.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(audit)) == 3
        assert db.scalar(select(func.count()).select_from(target_locks)) == 0


def test_disabled_expired_foreign_owner_account_cannot_write(context):
    c = context
    p = c.workflow.preview(UPDATE, "owner")
    c.settings.write_enabled = False
    with pytest.raises(ApiError, match="尚未启用"):
        c.workflow.execute(p["id"], "owner")
    c.settings.write_enabled = True
    with pytest.raises(ApiError) as error:
        c.workflow.execute(p["id"], "other")
    assert error.value.status == 404
    c.settings.account = "different-account"
    with pytest.raises(ApiError):
        c.workflow.execute(p["id"], "owner")
    assert c.workflow.list_jobs("owner") == []
    c.settings.account = "123456-sb1"
    with c.engine.begin() as db:
        db.execute(update(previews).where(previews.c.id == p["id"]).values(expires=millis() - 1))
    with pytest.raises(ApiError, match="过期"):
        c.workflow.execute(p["id"], "owner")
    assert not c.ns.writes


def test_changed_record_blocks_write_and_releases_lock(context):
    p = context.workflow.preview(UPDATE, "owner")
    context.ns.record["memo"] = "changed by another user"
    with pytest.raises(ApiError, match="已变化"):
        context.workflow.execute(p["id"], "owner")
    assert context.workflow.get(p["id"], "owner")["state"] == "preview"
    with context.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(target_locks)) == 0
    assert not context.ns.writes


def test_failed_preflight_does_not_poison_target(context):
    p = context.workflow.preview(UPDATE, "owner")
    context.ns.fail_read = True
    with pytest.raises(ApiError):
        context.workflow.execute(p["id"], "owner")
    context.ns.fail_read = False
    assert context.workflow.execute(p["id"], "owner")["state"] == "succeeded"


def test_unknown_is_durable_and_blocks_new_preview_for_same_target(context):
    c = context
    p, q = [c.workflow.preview(UPDATE, "owner") for _ in range(2)]
    c.ns.fail_write = True
    assert c.workflow.execute(p["id"], "owner")["state"] == "unknown"
    reopened = Workflow(c.settings, c.ns, c.engine)
    assert reopened.execute(p["id"], "owner")["state"] == "unknown"
    with pytest.raises(ApiError, match="执行中或结果未知"):
        reopened.execute(q["id"], "owner")
    assert len(c.ns.writes) == 1


def test_interrupted_is_not_reset_on_startup_and_offline_recovery_keeps_lock(context):
    c = context
    p = c.workflow.preview(UPDATE, "owner")
    assert c.workflow.claim(p, "owner")
    reopened = Workflow(c.settings, c.ns, c.engine)
    assert reopened.get(p["id"], "owner")["state"] == "executing"
    assert reopened.recover_interrupted() == 1
    assert reopened.execute(p["id"], "owner")["state"] == "unknown"
    with c.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(target_locks)) == 1
    assert not c.ns.writes


def test_concurrent_requests_do_not_overlap(context):
    c = context
    p, q = [c.workflow.preview(UPDATE, "owner") for _ in range(2)]
    entered, release = Event(), Event()

    def slow_token():
        entered.set()
        assert release.wait(5)
        return "token"

    c.ns.token = slow_token
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(c.workflow.execute, p["id"], "owner")
        assert entered.wait(5)
        try:
            assert c.workflow.execute(p["id"], "owner")["state"] == "executing"
            with pytest.raises(ApiError, match="执行中或结果未知"):
                c.workflow.execute(q["id"], "owner")
        finally:
            release.set()
        assert first.result()["state"] == "succeeded"
    assert len(c.ns.writes) == 1


def test_create_external_id_and_duplicate_detection(context):
    c = context
    body = {
        "operation": "create",
        "type": "vendorBill",
        "payload": {"externalId": "invoice_001", "memo": "核对"},
    }
    p = c.workflow.preview(body, "owner")
    assert p["before"] is None
    assert c.workflow.execute(p["id"], "owner")["state"] == "succeeded"
    assert c.ns.writes[0][:3] == ("POST", "vendorBill", None)
    with pytest.raises(ApiError, match="已存在"):
        c.workflow.preview(body, "owner")


@pytest.mark.parametrize(
    "patch",
    [
        {"payload": {"subsidiary": {"id": "99"}}},
        {"payload": {"id": "99"}},
        {"payload": {"externalId": "change-id"}},
        {"payload": []},
        {"payload": {"memo": float("nan")}},
        {"type": "customer"},
        {"id": "../customer"},
        {"id": "eid:1"},
        {"operation": "create"},
    ],
)
def test_reject_invalid_targets_and_payloads(context, patch):
    with pytest.raises(ApiError):
        context.workflow.preview({**UPDATE, **patch}, "owner")
    assert not context.ns.writes


def test_normalizes_internal_id_and_rejects_ns_id_mismatch(context):
    p = context.workflow.preview({**UPDATE, "id": "0001"}, "owner")
    assert p["target"] == "vendorBill/1"
    context.ns.record["id"] = "99"
    with pytest.raises(ApiError, match="ID 不匹配"):
        context.workflow.preview(UPDATE, "owner")
