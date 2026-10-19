"""群级守卫、人工回退和 HTTP 提交边界。"""

from copy import copy

import backend.app as app_module
import pytest
from backend.core.errors import ApiError
from backend.integrations.wecom_messaging import WeComRejected
from backend.modules.task.dto.delivery_dto import DeliveryRefreshRequest
from backend.tests.delivery_fixtures import delivery as delivery
from backend.tests.delivery_fixtures import request
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_task import USER, FakeWecom, approve, draft, prepare_all, record
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved
from fastapi.testclient import TestClient
from sqlalchemy import text


def second_task(delivery, ns, engine):
    save(ns, engine, bundle([purchase(), purchase("201", "871")], [customs("870"), customs("871")]))
    approve(delivery.services, "CD871")
    with engine.connect() as connection:
        task_id = connection.execute(text("SELECT MAX(id) FROM task_tasks")).scalar()
    prepare_all(delivery.services, task_id)
    delivery.services["notifications"].save_draft(task_id, draft(), USER)
    result = copy(delivery)
    result.task_id = task_id
    return result


def test_same_group_different_tasks_and_daily_quota(delivery, ns, engine):
    other = second_task(delivery, ns, engine)
    body = request(other)
    first = delivery.submit.submit(delivery.task_id, request(delivery), USER)
    with pytest.raises(ApiError, match="客户群有未决"):
        other.submit.submit(other.task_id, body, USER)
    delivery.channel.success()
    delivery.receipts.refresh(delivery.task_id, DeliveryRefreshRequest(deliveryId=first.id), USER)
    with pytest.raises(ApiError, match="当日提交上限"):
        other.submit.submit(other.task_id, body, USER)
    assert len(delivery.channel.creates) == 1


def test_definite_failure_allows_manual_channel_with_correct_label(delivery):
    delivery.channel.create_error = WeComRejected(48002)
    assert delivery.submit.submit(delivery.task_id, request(delivery), USER).status == "failed"
    detail = delivery.services["notifications"].record(delivery.task_id, record(), USER)
    assert detail.notification.history[0].channel == "manual"
    assert detail.notification.statusLabel == "人工登记已发送"


def test_source_change_during_upload_stops_create(delivery, ns, engine):
    delivery.channel.after_upload = lambda: save(
        ns, engine, bundle([purchase(amounts=("99.00", "20.00"))], [customs("870")])
    )
    assert delivery.submit.submit(delivery.task_id, request(delivery), USER).status == "failed"
    assert not delivery.channel.creates


def test_api_auth_strict_payload_and_delivery_ownership(delivery, engine, context, monkeypatch):
    settings = delivery.settings
    settings.admin_password = "test-only-password"
    monkeypatch.setattr(app_module, "WeComMessaging", lambda _: delivery.channel)
    app = app_module.create_app(settings, context.ns, engine, wecom=FakeWecom())
    monkeypatch.setattr(app.state.contract_worker, "start", lambda: None)
    monkeypatch.setattr(app.state.contract_worker, "stop", lambda: None)
    root = f"/api/tasks/{delivery.task_id}/notification"
    with TestClient(app) as client:
        assert client.get(root + "/delivery").status_code == 401
        headers = {"Origin": settings.origin}
        assert (
            client.post(
                "/api/session",
                headers=headers,
                json={"username": "admin", "password": settings.admin_password},
            ).status_code
            == 200
        )
        assert (
            client.post(
                root + "/preview",
                headers=headers,
                json={"revision": 1, "groupRevision": 1, "chatId": "forged"},
            ).status_code
            == 400
        )
        preview = client.post(root + "/preview", headers=headers, json={"revision": 1, "groupRevision": 1})
        assert preview.status_code == 200 and "path" not in preview.text.lower()
        body = {
            "revision": 1,
            "groupRevision": 1,
            "snapshotSha256": preview.json()["snapshotSha256"],
            "requestId": "http-test-request",
        }
        result = client.post(root + "/submit", headers=headers, json=body)
        assert result.status_code == 200 and result.json()["status"] == "pending_confirmation"
        assert (
            client.post(
                "/api/tasks/999/notification/refresh",
                headers=headers,
                json={"deliveryId": result.json()["id"]},
            ).status_code
            == 404
        )
        assert client.post(root + "/submit", headers=headers, json=body).json()["id"] == result.json()["id"]
        assert len(delivery.channel.creates) == 1
