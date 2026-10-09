"""通知真实持久化、快照保护与人工登记；使用隔离数据库和临时合同目录。"""

from datetime import UTC, datetime, timedelta

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.business.entity import load_tables
from backend.modules.reconciliation import notification_dao
from backend.modules.reconciliation.dto import TaskListQuery
from backend.modules.reconciliation.notification_dto import NotificationDraft, NotificationRecord
from backend.modules.reconciliation.task_service import InvoiceTaskService
from backend.tests.test_api import login
from backend.tests.test_finance_list import OWNER
from backend.tests.test_invoice_tasks import approve
from backend.tests.test_task_documents import ContractSource, task_service
from backend.tests.test_task_documents import local_source as local_source
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError


def draft(revision=0, **overrides):
    return NotificationDraft(
        revision=revision,
        **{
            "groupName": "供应商外部群",
            "employee": "采购员",
            "message": "请按合同开票，谢谢。",
            **overrides,
        },
    )


def record(revision=1, **overrides):
    return NotificationRecord(
        revision=revision,
        **{
            "sentAt": datetime.now(UTC),
            "note": "已核实群并发送正文与合同",
            "confirmed": True,
            **overrides,
        },
    )


def test_draft_and_record_persist_with_immutable_snapshot(context, local_source):
    service, task, order = task_service(context, local_source, ContractSource())
    initial = service.detail(task.id, OWNER)
    assert task.recordNumber in initial.notification.defaultMessage
    assert initial.notification.revision == 0 and not initial.notification.record.allowed
    saved = service.save_notification(task.id, draft(), OWNER)
    assert saved.notification.revision == 1 and saved.task.status == "documents_pending"
    service.prepare_document(task.id, order, OWNER)
    request = record()
    sent = service.save_notification(task.id, request, OWNER, record=True)
    assert sent.task.status == "awaiting_invoice"
    assert sent.steps[2].state == "done" and sent.steps[3].state == "current"
    assert sent.notification.statusLabel == "人工登记已发送" and not sent.notification.send.allowed
    assert not sent.notification.edit.allowed and not sent.notification.record.allowed
    assert sent.notification.history[0].attachments == [sent.documents[0].filename]
    again = service.save_notification(task.id, request, OWNER, record=True)
    assert len(again.notification.history) == 2
    reloaded = InvoiceTaskService(context.engine, local_source).detail(task.id, OWNER)
    assert reloaded.notification.history == sent.notification.history
    with pytest.raises(ApiError):
        service.save_notification(task.id, draft(2, message="修改历史"), OWNER)
    with pytest.raises(ApiError):
        service.save_notification(task.id, record(note="另一次发送"), OWNER, record=True)
    counts = service.browse(TaskListQuery(), OWNER).counts
    assert counts.awaitingInvoice == 1 and counts.needsAttention == 0


def test_ownership_stale_revision_and_missing_documents(context, local_source):
    service, task, _ = task_service(context, local_source, ContractSource())
    with pytest.raises(ApiError) as error:
        service.save_notification(task.id, draft(), "user:other")
    assert error.value.status == 404
    service.save_notification(task.id, draft(), OWNER)
    with pytest.raises(ApiError) as error:
        service.save_notification(task.id, draft(message="并发覆盖"), OWNER)
    assert error.value.status == 409
    with pytest.raises(ApiError):
        service.save_notification(task.id, record(), OWNER, record=True)
    assert len(service.detail(task.id, OWNER).notification.history) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"sentAt": datetime.now(UTC) + timedelta(days=1)},
        {"sentAt": datetime(2020, 1, 1, tzinfo=UTC)},
        {"sentAt": datetime.now()},
        {"note": "   "},
        {"confirmed": False},
    ],
)
def test_invalid_manual_registration_does_not_advance(context, local_source, overrides):
    service, task, order = task_service(context, local_source, ContractSource())
    service.prepare_document(task.id, order, OWNER)
    service.save_notification(task.id, draft(), OWNER)
    with pytest.raises(ApiError):
        service.save_notification(task.id, record(**overrides), OWNER, record=True)
    assert service.detail(task.id, OWNER).task.status == "notify_pending"


def test_changed_and_superseded_source_blocks_saving(context, local_source):
    service, task, _ = task_service(context, local_source, ContractSource())
    service.save_notification(task.id, draft(), OWNER)
    with local_source.engine.begin() as connection:
        lines = load_tables(connection)["purchase_order_lines"]
        connection.execute(lines.update().where(lines.c.id == 1).values(quantity="101"))
    assert not service.detail(task.id, OWNER).notification.edit.allowed
    with pytest.raises(ApiError):
        service.save_notification(task.id, draft(1), OWNER)
    approve(context, local_source)
    with pytest.raises(ApiError):
        service.save_notification(task.id, draft(1), OWNER)
    assert service.detail(task.id, OWNER).notification.history[0].message == draft().message


def test_failed_history_append_rolls_back_status(context, local_source, monkeypatch):
    service, task, order = task_service(context, local_source, ContractSource())
    service.prepare_document(task.id, order, OWNER)
    service.save_notification(task.id, draft(), OWNER)

    def fail(*args):
        raise SQLAlchemyError("simulated failure")

    monkeypatch.setattr(notification_dao, "append", fail)
    with pytest.raises(ApiError):
        service.save_notification(task.id, record(), OWNER, record=True)
    assert service.detail(task.id, OWNER).task.status == "notify_pending"


def test_http_auth_validation_and_real_save(context, local_source):
    service, task, order = task_service(context, local_source, ContractSource())
    service.prepare_document(task.id, order, OWNER)
    app = create_app(context.settings, context.ns, context.engine, local_source.engine)
    path = f"/api/reconciliation/invoice-tasks/{task.id}/notification/draft"
    headers = {"Origin": context.settings.origin}
    with TestClient(app) as client:
        assert client.post(path, json=draft().model_dump(), headers=headers).status_code == 401
        login(client, context)
        assert client.post(path, json={"revision": -1}, headers=headers).status_code == 400
        response = client.post(path, json=draft().model_dump(), headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["notification"]["groupName"] == "供应商外部群"
        response = client.post(
            path.replace("/draft", "/record"), json=record().model_dump(mode="json"), headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["task"]["status"] == "awaiting_invoice"
