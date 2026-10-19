"""真实服务隔离验证：版本、文件、幂等、未知结果和渠道回执不误推进。"""

from datetime import timedelta
from pathlib import Path

import pytest
from backend.core.errors import ApiError
from backend.integrations.wecom_messaging import WeComRejected
from backend.modules.task.dto.delivery_dto import DeliveryPreviewRequest, DeliveryRefreshRequest
from backend.modules.task.service.delivery_state import now
from backend.tests.delivery_fixtures import delivery as delivery
from backend.tests.delivery_fixtures import request
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_task import USER, draft, record
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved
from sqlalchemy import text


def submit(delivery):
    return delivery.submit.submit(delivery.task_id, request(delivery), USER)


def refresh(delivery, item):
    return delivery.receipts.refresh(delivery.task_id, DeliveryRefreshRequest(deliveryId=item.id), USER)


def test_preview_submit_and_receipt_are_separate(delivery, engine):
    body = request(delivery)
    assert not delivery.channel.uploads and not delivery.channel.creates
    item = delivery.submit.submit(delivery.task_id, body, USER)
    assert item.status == "pending_confirmation"
    assert delivery.services["tasks"].detail(delivery.task_id).task.status == "notify_pending"
    assert delivery.submit.submit(delivery.task_id, body, USER).id == item.id
    assert len(delivery.channel.creates) == 1
    with pytest.raises(ApiError, match="不一致"):
        delivery.submit.submit(delivery.task_id, body.model_copy(update={"snapshotSha256": "0" * 64}), USER)
    with pytest.raises(ApiError, match="未决"):
        delivery.services["notifications"].save_draft(delivery.task_id, draft(revision=1), USER)
    with pytest.raises(ApiError, match="未决"):
        delivery.services["notifications"].record(delivery.task_id, record(), USER)
    delivery.channel.success()
    assert refresh(delivery, item).status == "sent"
    detail = delivery.services["tasks"].detail(delivery.task_id)
    assert detail.task.status == "awaiting_invoice" and detail.notification.history[0].channel == "wecom"
    assert "企微" in detail.steps[2].description
    assert refresh(delivery, item).status == "sent"
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM task_events WHERE reason='企微已确认目标群发送'")
            ).scalar()
            == 2
        )
        assert (
            connection.execute(text("SELECT active_delivery_id FROM task_notification_group_guards")).scalar()
            is None
        )


@pytest.mark.parametrize(
    "error,status", [(ApiError(502, "连接超时"), "unknown"), (WeComRejected(48002), "failed")]
)
def test_create_error_classification_and_restart(delivery, error, status):
    body = request(delivery)
    delivery.channel.create_error = error
    item = delivery.submit.submit(delivery.task_id, body, USER)
    assert item.status == status
    assert delivery.submit.submit(delivery.task_id, body, USER).id == item.id
    assert len(delivery.channel.creates) == 1
    if status == "unknown":
        with pytest.raises(ApiError, match="未决"):
            request(delivery)
    else:
        assert delivery.services["tasks"].detail(delivery.task_id).notification.edit.allowed


def test_upload_failure_never_creates(delivery):
    delivery.channel.upload_error = ApiError(502, "上传失败")
    assert submit(delivery).status == "failed"
    assert not delivery.channel.creates


@pytest.mark.parametrize("change", ["content", "missing", "outside", "unarchived"])
def test_contract_validation(delivery, engine, tmp_path, change):
    body = request(delivery)
    detail = delivery.services["tasks"].detail(delivery.task_id)
    path = Path(detail.documents[0].archivePath)
    if change == "content":
        path.write_bytes(b"changed")
    elif change == "missing":
        path.unlink()
    else:
        outside = tmp_path / "outside.pdf"
        outside.write_bytes(path.read_bytes())
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE task_documents SET archive_path=:path, status=:status"),
                {
                    "path": str(outside) if change == "outside" else str(path),
                    "status": "pending" if change == "unarchived" else "archived",
                },
            )
    with pytest.raises(ApiError):
        delivery.submit.submit(delivery.task_id, body, USER)
    assert not delivery.channel.creates and not delivery.channel.uploads


@pytest.mark.parametrize("change", ["owner", "corp", "notification", "switch"])
def test_stale_preview_and_switch(delivery, change):
    body = request(delivery)
    if change == "owner":
        delivery.channel.owner = "new-owner"
    elif change == "corp":
        delivery.channel.corp = "other-corp"
    elif change == "notification":
        delivery.services["notifications"].save_draft(
            delivery.task_id, draft(revision=1, message="新版本"), USER
        )
    else:
        delivery.settings.wecom_send_enabled = False
    with pytest.raises(ApiError):
        delivery.submit.submit(delivery.task_id, body, USER)
    assert not delivery.channel.creates


def test_owner_changes_during_upload(delivery):
    delivery.channel.after_upload = lambda: setattr(delivery.channel, "owner", "new-owner")
    assert submit(delivery).status == "failed"
    assert not delivery.channel.creates


@pytest.mark.parametrize(
    "results",
    [
        [],
        [{"chat_id": "other", "userid": "zhangsan", "status": 1, "send_time": 1700000000}],
        [{"chat_id": "wr001", "userid": "zhangsan", "status": 99}],
        [{"chat_id": "wr001", "userid": "someone", "status": 1, "send_time": 1700000000}],
        [{"chat_id": "wr001", "userid": "zhangsan", "status": 1}],
    ],
)
def test_non_evidence_does_not_advance(delivery, results):
    item = submit(delivery)
    delivery.channel.receipts = results
    assert refresh(delivery, item).status == "pending_confirmation"
    assert delivery.services["tasks"].detail(delivery.task_id).task.status == "notify_pending"


def test_read_failure_keeps_pending_and_backoff(delivery):
    item = submit(delivery)
    delivery.channel.query_error = ApiError(502, "网络不可用")
    result = refresh(delivery, item)
    assert result.status == "pending_confirmation" and result.msgid == item.msgid
    assert result.nextCheckAt > result.lastCheckedAt and "网络" in result.error


@pytest.mark.parametrize("status", ["completed", "partially_received", "superseded"])
def test_late_receipt_never_regresses_or_transfers_task(delivery, engine, status):
    item = submit(delivery)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE task_tasks SET status=:status WHERE id=:id"),
            {"status": status, "id": delivery.task_id},
        )
    delivery.channel.success()
    assert refresh(delivery, item).status == "sent"
    assert delivery.services["tasks"].detail(delivery.task_id).task.status == status


@pytest.mark.parametrize("phase,target", [("preparing", "failed"), ("submitting", "unknown")])
def test_interrupted_execution_recovery(delivery, engine, phase, target):
    body = request(delivery)
    frozen, _, group = delivery.submit._prepare(delivery.task_id, body)
    item, _ = delivery.submit._claim(delivery.task_id, body, USER, frozen, group)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE task_notification_deliveries SET status=:status, lease_expires_at=:at"),
            {"status": phase, "at": now() - timedelta(seconds=1)},
        )
    result = delivery.receipts.refresh(
        delivery.task_id, DeliveryRefreshRequest(deliveryId=str(item["id"])), USER
    )
    assert result.status == target and not delivery.channel.creates
    with pytest.raises(ApiError):
        delivery.submit._before_create(delivery.task_id, body, item, ["media"], group, USER)


def test_permissions_and_utf8_limit(delivery):
    with pytest.raises(ApiError, match="只读"):
        delivery.submit.preview(
            delivery.task_id, DeliveryPreviewRequest(revision=1, groupRevision=1), "service:test"
        )
    delivery.services["notifications"].save_draft(
        delivery.task_id, draft(revision=1, message="中" * 1400), USER
    )
    with pytest.raises(ApiError, match="4000"):
        delivery.submit.preview(delivery.task_id, DeliveryPreviewRequest(revision=2, groupRevision=1), USER)
