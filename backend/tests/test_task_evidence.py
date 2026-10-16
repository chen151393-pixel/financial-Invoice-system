"""迁移旧合同/通知的关键回归到 task：失败重试、来源失效、历史与事务回滚。"""

from pathlib import Path

import pytest
from backend.core.errors import ApiError
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_task import USER, draft, prepare_all, record
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved
from sqlalchemy.exc import SQLAlchemyError


def first_order(services, task_id):
    return int(services["tasks"].detail(task_id).documents[0].orderId)


def test_archive_retry_retains_first_fetch_and_refuses_changed_pdf(
    engine, app_services, approved, monkeypatch
):
    service = app_services["documents"]
    original = service.archive.save

    def fail(*args):
        raise ApiError(503, "隔离共享盘暂时不可用")

    monkeypatch.setattr(service.archive, "save", fail)
    order = first_order(app_services, approved["id"])
    with pytest.raises(ApiError):
        service.prepare(approved["id"], order, USER)
    first = rows(engine, "SELECT * FROM task_documents")[0]
    assert first["status"] == "failed" and "content" not in first
    app_services["contracts"].content += b"changed"
    monkeypatch.setattr(service.archive, "save", original)
    with pytest.raises(ApiError, match="首次"):
        service.prepare(approved["id"], order, USER)
    app_services["contracts"].content = b"%PDF-1.4 contract"
    service.prepare(approved["id"], order, USER)
    saved = rows(engine, "SELECT * FROM task_documents")[0]
    assert saved["created_at"] == first["created_at"] and saved["status"] == "archived"
    assert Path(saved["archive_path"]).read_bytes() == app_services["contracts"].content


def test_source_changes_during_download_do_not_register(ns, engine, app_services, approved, monkeypatch):
    original = app_services["contracts"].download

    def changed(*args):
        value = original(*args)
        save(ns, engine, bundle([purchase(amounts=("110.50", "20.00"))], [customs("870")]))
        return value

    monkeypatch.setattr(app_services["contracts"], "download", changed)
    with pytest.raises(ApiError, match="来源"):
        app_services["documents"].prepare(approved["id"], first_order(app_services, approved["id"]), USER)
    assert rows(engine, "SELECT id FROM task_documents") == []
    with pytest.raises(ApiError, match="来源"):
        app_services["notifications"].save_draft(approved["id"], draft(), USER)


def test_notification_state_event_failure_rolls_back_sent_record(engine, app_services, approved, monkeypatch):
    prepare_all(app_services, approved["id"])
    service = app_services["notifications"]
    service.save_draft(approved["id"], draft(), USER)
    before = rows(engine, "SELECT * FROM task_notifications")
    from backend.modules.task.dao import event_dao

    def fail(*args):
        raise SQLAlchemyError("isolated event failure")

    with monkeypatch.context() as scope:
        scope.setattr(event_dao, "append", fail)
        with pytest.raises(ApiError):
            service.record(approved["id"], record(), USER)
    assert rows(engine, "SELECT * FROM task_notifications") == before
    request = record()
    service.record(approved["id"], request, USER)
    sent = rows(engine, "SELECT * FROM task_notifications")
    service.record(approved["id"], request, USER)
    assert rows(engine, "SELECT * FROM task_notifications") == sent
    with pytest.raises(ApiError):
        service.save_draft(approved["id"], draft(1, message="不能改历史"), USER)
