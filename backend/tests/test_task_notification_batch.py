"""批量登记线下已通知：逐任务结果、登记时间取服务器当时、草稿复用、跳过原因、任务台能力、HTTP 与页面授权。"""

from datetime import UTC, date, datetime, timedelta

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.task.dto.notification_dto import NotificationBatchRecord
from backend.modules.task.dto.task_dto import TaskBoardQuery
from backend.modules.task.policy.notification_policy import OFFLINE_CONTENT, OFFLINE_NOTE
from backend.modules.task.service.task_board_service import TaskBoardService
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_task import USER, FakeWecom, approve, draft, prepare_all, task_rows
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved
from backend.tests.test_task import engine as engine
from backend.tests.test_task import ns as ns
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text


def batch(*task_ids, note=""):
    return NotificationBatchRecord(taskIds=[str(value) for value in task_ids], note=note)


def notices(engine):
    return rows(engine, "SELECT * FROM task_notifications ORDER BY task_id, version")


def test_batch_records_ready_task_with_server_time(engine, app_services, approved):
    services, task_id = app_services, approved["id"]
    prepare_all(services, task_id)
    before = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    result = services["notifications"].record_batch(batch(task_id), USER)
    assert [item.id for item in result.recorded] == [str(task_id)] and not result.skipped
    saved = notices(engine)
    assert len(saved) == 1 and saved[0]["status"] == "sent" and saved[0]["channel"] == "manual"
    assert saved[0]["content"] == OFFLINE_CONTENT and saved[0]["note"] == OFFLINE_NOTE
    assert saved[0]["sent_by"] == USER and saved[0]["sender_name"] == USER
    sent_at = datetime.fromisoformat(str(saved[0]["sent_at"]))
    assert before <= sent_at <= datetime.now(UTC).replace(tzinfo=None)
    detail = services["tasks"].detail(task_id)
    assert detail.task.status == "awaiting_invoice" and detail.notification.statusLabel == "人工登记已发送"
    assert not detail.notification.edit.allowed
    events = rows(engine, "SELECT * FROM task_events ORDER BY id")
    assert (events[-1]["to_status"], events[-1]["actor"], events[-1]["reason"]) == (
        "awaiting_invoice",
        USER,
        OFFLINE_NOTE,
    )
    # 重复提交不产生第二条记录，按已登记跳过
    again = services["notifications"].record_batch(batch(task_id), USER)
    assert not again.recorded and "无需重复登记" in again.skipped[0].reason
    assert len(notices(engine)) == 1


def test_batch_reuses_saved_draft_and_keeps_its_content(engine, app_services, approved):
    services, task_id = app_services, approved["id"]
    prepare_all(services, task_id)
    services["notifications"].save_draft(task_id, draft(message="请按合同开票"), USER)
    result = services["notifications"].record_batch(batch(task_id, note="电话已通知"), USER)
    assert result.recorded and not result.skipped
    saved = notices(engine)
    assert len(saved) == 1 and saved[0]["status"] == "sent" and saved[0]["content"] == "请按合同开票"
    assert saved[0]["recipient_name"] == "上海供应商开票群" and saved[0]["note"] == "电话已通知"


def test_batch_saves_selected_china_date_and_keeps_real_audit_time(engine, app_services, approved):
    task_id = approved["id"]
    prepare_all(app_services, task_id)
    selected = (datetime.now(UTC) + timedelta(hours=8)).date() - timedelta(days=2)
    created_at = datetime.combine(selected - timedelta(days=1), datetime.min.time())
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE task_tasks SET created_at=:created WHERE id=:id"),
            {"created": created_at, "id": task_id},
        )
    before = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    body = NotificationBatchRecord(taskIds=[str(task_id)], notifiedOn=selected)
    result = app_services["notifications"].record_batch(body, USER)
    assert result.recorded and not result.skipped
    saved = notices(engine)[0]
    sent_at = datetime.fromisoformat(str(saved["sent_at"]))
    assert sent_at == datetime.combine(selected, datetime.min.time()) - timedelta(hours=8)
    assert datetime.fromisoformat(str(saved["updated_at"])) >= before
    events = rows(engine, "SELECT * FROM task_events ORDER BY id")
    assert datetime.fromisoformat(str(events[-1]["occurred_at"])) >= before


def test_batch_rejects_future_and_skips_date_before_task_creation(engine, app_services, approved):
    task_id = approved["id"]
    prepare_all(app_services, task_id)
    today = (datetime.now(UTC) + timedelta(hours=8)).date()
    with pytest.raises(ApiError, match="通知日期不能晚于今天"):
        app_services["notifications"].record_batch(
            NotificationBatchRecord(taskIds=[str(task_id)], notifiedOn=today + timedelta(days=1)), USER
        )
    assert not notices(engine)
    result = app_services["notifications"].record_batch(
        NotificationBatchRecord(taskIds=[str(task_id)], notifiedOn=date(2000, 1, 1)), USER
    )
    assert not result.recorded and "早于任务生成日期" in result.skipped[0].reason
    assert not notices(engine)


@pytest.mark.parametrize("value", ["", "2026-02-30", "20261119", "2026-W47-4", "2026-11-19T12:00:00Z", 123])
def test_batch_rejects_invalid_notification_date(value):
    with pytest.raises(ValidationError):
        NotificationBatchRecord(taskIds=["1"], notifiedOn=value)


def test_batch_skips_blocked_tasks_without_stopping_others(ns, engine, app_services):
    save(ns, engine, bundle([purchase(), purchase("201", "871")], [customs("870"), customs("871")]))
    approve(app_services, "CD870")
    approve(app_services, "CD871")
    first, second = task_rows(engine)
    prepare_all(app_services, second["id"])
    result = app_services["notifications"].record_batch(batch(first["id"], second["id"], 999999), USER)
    assert [item.id for item in result.recorded] == [str(second["id"])]
    reasons = {item.id: item.reason for item in result.skipped}
    assert "共享盘" in reasons[str(first["id"])] and "不存在" in reasons["999999"]
    statuses = {row["id"]: row["status"] for row in task_rows(engine)}
    assert statuses == {first["id"]: "documents_pending", second["id"]: "awaiting_invoice"}
    assert [row["task_id"] for row in notices(engine)] == [second["id"]]


def test_batch_rejects_service_identity_and_invalid_requests(app_services, approved):
    with pytest.raises(ApiError) as error:
        app_services["notifications"].record_batch(batch(approved["id"]), "service:bot")
    assert error.value.status == 403
    for ids in ([], ["1", "1"], ["0"], ["abc"], ["-1"], [str(value) for value in range(1, 52)]):
        with pytest.raises(ValidationError):
            NotificationBatchRecord(taskIds=ids)
    with pytest.raises(ValidationError):
        NotificationBatchRecord(taskIds=["1"], note="长" * 301)


def test_board_exposes_batch_record_capability(engine, app_services, approved):
    services, task_id = app_services, approved["id"]
    board = TaskBoardService(engine, services["tasks"].directory, services["tasks"])
    waiting = board.browse(TaskBoardQuery()).items[0].notifyRecord
    assert not waiting.allowed and "共享盘" in waiting.reason
    prepare_all(services, task_id)
    assert board.browse(TaskBoardQuery()).items[0].notifyRecord.allowed
    services["notifications"].record_batch(batch(task_id), USER)
    after = board.browse(TaskBoardQuery()).items[0]
    assert after.currentNode == "invoices" and not after.notifyRecord.allowed
    assert "无需重复登记" in after.notifyRecord.reason


def test_batch_record_http(context, ns, engine):
    app = create_app(context.settings, context.ns, engine, wecom=FakeWecom())
    path = "/api/tasks/notification/record-batch"
    with TestClient(app) as client:
        assert client.post(path, json={"taskIds": ["1"]}).status_code == 401
        headers = {"Origin": context.settings.origin}
        client.post(
            "/api/session",
            headers=headers,
            json={"username": "admin", "password": context.settings.admin_password},
        )
        response = client.post(path, json={"taskIds": ["1"]}, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"recorded": [], "skipped": [{"id": "1", "reason": "开票任务不存在"}]}
        # 发送时间不由页面提交
        extra = client.post(path, json={"taskIds": ["1"], "sentAt": "2026-01-01"}, headers=headers)
        assert extra.status_code in (400, 422)
