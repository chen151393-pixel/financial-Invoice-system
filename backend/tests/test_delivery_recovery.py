"""未知结果证据关联、落库中断、来源替代与身份边界。"""

from datetime import UTC, timedelta

import pytest
from backend.core.errors import ApiError
from backend.modules.task.dto.delivery_dto import DeliveryReconcileRequest, DeliveryRefreshRequest
from backend.modules.task.service.delivery_state import now
from backend.tests.delivery_fixtures import delivery as delivery
from backend.tests.delivery_fixtures import request
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_task import USER, approve, draft, prepare_all
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


def unknown(delivery):
    delivery.channel.create_error = ApiError(502, "超时")
    item = delivery.submit.submit(delivery.task_id, request(delivery), USER)
    row = delivery.receipts.read(delivery.task_id, item.id)
    delivery.channel.record_list = [
        {
            "msgid": "recovered-msg",
            "create_type": 0,
            "create_time": int(row["submitted_at"].replace(tzinfo=UTC).timestamp()),
            "text": {"content": row["snapshot_json"]["message"]},
            "attachments": [
                {"msgtype": "file", "file": {"media_id": media}} for media in row["evidence_json"]["mediaIds"]
            ],
        }
    ]
    return item


def test_reconciliation_requires_complete_unique_evidence(delivery):
    item = unknown(delivery)
    assert not delivery.reconcile.candidates(delivery.task_id, item.id, USER).items
    delivery.channel.success()
    candidate = delivery.reconcile.candidates(delivery.task_id, item.id, USER).items[0]
    body = DeliveryReconcileRequest(
        deliveryId=item.id,
        candidateId=candidate.candidateId,
        evidenceSha256=candidate.evidenceSha256,
        reason="已向群主核实原任务",
    )
    with pytest.raises(ApiError, match="证据"):
        delivery.reconcile.reconcile(
            delivery.task_id, body.model_copy(update={"candidateId": "arbitrary"}), USER
        )
    assert delivery.reconcile.reconcile(delivery.task_id, body, USER).status == "pending_confirmation"
    assert delivery.reconcile.reconcile(delivery.task_id, body, USER).msgid == "recovered-msg"
    result = delivery.receipts.refresh(delivery.task_id, DeliveryRefreshRequest(deliveryId=item.id), USER)
    assert result.status == "sent" and len(delivery.channel.creates) == 1


def test_ambiguous_records_do_not_unlock(delivery):
    item = unknown(delivery)
    delivery.channel.success()
    delivery.channel.record_list *= 2
    assert not delivery.reconcile.candidates(delivery.task_id, item.id, USER).items
    assert delivery.receipts.read(delivery.task_id, item.id)["status"] == "unknown"


def test_channel_acceptance_then_database_failure_keeps_guard(delivery, engine, monkeypatch):
    body = request(delivery)
    original = delivery.submit._finish
    monkeypatch.setattr(
        delivery.submit,
        "_finish",
        lambda *args: (_ for _ in ()).throw(OperationalError("test", {}, Exception("offline"))),
    )
    with pytest.raises(ApiError, match="待核实"):
        delivery.submit.submit(delivery.task_id, body, USER)
    row = delivery.receipts.history(delivery.task_id).items[0]
    assert row.status == "submitting" and len(delivery.channel.creates) == 1
    monkeypatch.setattr(delivery.submit, "_finish", original)
    assert delivery.submit.submit(delivery.task_id, body, USER).id == row.id
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE task_notification_deliveries SET lease_expires_at=:at"),
            {"at": now() - timedelta(seconds=1)},
        )
    assert (
        delivery.receipts.refresh(delivery.task_id, DeliveryRefreshRequest(deliveryId=row.id), USER).status
        == "unknown"
    )
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT active_delivery_id FROM task_notification_group_guards")
        ).scalar() == int(row.id)


def test_new_task_and_group_cannot_bypass_predecessor(delivery, ns, engine):
    item = unknown(delivery)
    save(ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")]))
    approve(delivery.services, "CD870")
    with engine.connect() as connection:
        successor = connection.execute(text("SELECT MAX(id) FROM task_tasks")).scalar()
    prepare_all(delivery.services, successor)
    with pytest.raises(ApiError, match="未决"):
        delivery.services["notifications"].save_draft(successor, draft(), USER)
    delivery.channel.success()
    candidate = delivery.reconcile.candidates(delivery.task_id, item.id, USER).items[0]
    delivery.reconcile.reconcile(
        delivery.task_id,
        DeliveryReconcileRequest(
            deliveryId=item.id,
            candidateId=candidate.candidateId,
            evidenceSha256=candidate.evidenceSha256,
            reason="核实旧任务",
        ),
        USER,
    )
    delivery.receipts.refresh(delivery.task_id, DeliveryRefreshRequest(deliveryId=item.id), USER)
    assert delivery.services["tasks"].detail(successor).task.status == "notify_pending"


def test_identity_and_task_ownership(delivery):
    item = delivery.submit.submit(delivery.task_id, request(delivery), USER)
    with pytest.raises(ApiError, match="只读"):
        delivery.receipts.refresh(
            delivery.task_id, DeliveryRefreshRequest(deliveryId=item.id), "service:readonly"
        )
    with pytest.raises(ApiError, match="不存在"):
        delivery.receipts.refresh(999, DeliveryRefreshRequest(deliveryId=item.id), USER)


def test_read_receipts_with_send_disabled(delivery):
    item = delivery.submit.submit(delivery.task_id, request(delivery), USER)
    delivery.settings.wecom_send_enabled = False
    delivery.channel.success()
    assert (
        delivery.receipts.refresh(delivery.task_id, DeliveryRefreshRequest(deliveryId=item.id), USER).status
        == "sent"
    )


def test_frozen_bytes_are_uploaded_even_if_file_replaced(delivery, monkeypatch):
    body = request(delivery)
    original = delivery.submit._claim

    def claim(*args):
        row, claimed = original(*args)
        from pathlib import Path

        Path(row["snapshot_json"]["documents"][0]["path"]).write_bytes(b"replacement")
        return row, claimed

    monkeypatch.setattr(delivery.submit, "_claim", claim)
    assert delivery.submit.submit(delivery.task_id, body, USER).status == "pending_confirmation"
    assert delivery.channel.uploads[0][1] == delivery.services["contracts"].content
