"""隔离验证审核提交后的自动合同归档，不访问真实 NS 或共享盘。"""

from pathlib import Path

import pytest
from backend.core.errors import ApiError
from backend.modules.review.public import ReviewApproved
from backend.modules.task.service.contract_worker import ContractWorker
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_task import USER, approve, task_rows
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved


def worker(services, engine):
    return ContractWorker(engine, services["documents"])


def test_approval_queues_once_and_downloads_after_commit(engine, ns, app_services, monkeypatch):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(app_services, "CD870")
    approve(app_services, "CD870")
    assert len(rows(engine, "SELECT * FROM task_contract_jobs")) == 1
    assert not app_services["contracts"].calls
    original = app_services["contracts"].download

    def download(*args):
        assert rows(engine, "SELECT status FROM review_records")[0]["status"] == "active"
        assert task_rows(engine)[0]["status"] == "documents_pending"
        return original(*args)

    monkeypatch.setattr(app_services["contracts"], "download", download)
    worker(app_services, engine).run_once()
    assert task_rows(engine)[0]["status"] == "notify_pending"
    job = rows(engine, "SELECT * FROM task_contract_jobs")[0]
    assert job["status"] == "completed" and job["actor"] == USER
    doc = rows(engine, "SELECT * FROM task_documents")[0]
    assert Path(doc["archive_path"]).read_bytes() == app_services["contracts"].content
    worker(app_services, engine).run_once()
    assert len(app_services["contracts"].calls) == 1


def test_review_rollback_never_leaves_jobs(engine, ns, app_services):
    def fail(connection, event):
        raise RuntimeError("隔离审核订阅失败")

    app_services["review"].events.subscribe(ReviewApproved, fail)
    save(ns, engine, bundle([purchase()], [customs("870")]))
    with pytest.raises(RuntimeError, match="订阅失败"):
        approve(app_services, "CD870")
    assert not rows(engine, "SELECT * FROM task_contract_jobs")
    assert not task_rows(engine)
    worker(app_services, engine).run_once()
    assert not app_services["contracts"].calls


@pytest.mark.parametrize("stage", ["download", "archive", "config"])
def test_failure_is_visible_and_manual_retry_completes(engine, app_services, approved, monkeypatch, stage):
    service = app_services["documents"]

    def fail(*args):
        raise ApiError(503, "隔离网络故障")

    with monkeypatch.context() as patch:
        if stage == "download":
            patch.setattr(app_services["contracts"], "download", fail)
        elif stage == "archive":
            patch.setattr(service.archive, "save", fail)
        else:
            patch.setattr(service.archive, "root", None)
        worker(app_services, engine).run_once()
    assert task_rows(engine)[0]["status"] == "documents_pending"
    assert rows(engine, "SELECT status FROM review_records")[0]["status"] == "active"
    job = rows(engine, "SELECT * FROM task_contract_jobs")[0]
    assert job["status"] == "failed" and job["error_message"]
    detail = app_services["tasks"].detail(approved["id"])
    assert detail.documents[0].status == "failed" and detail.documents[0].error
    calls = len(app_services["contracts"].calls)
    worker(app_services, engine).run_once()
    assert len(app_services["contracts"].calls) == calls  # 失败不会无限自动重试
    service.prepare(approved["id"], int(detail.documents[0].orderId), USER)
    assert rows(engine, "SELECT status FROM task_contract_jobs")[0]["status"] == "completed"
    assert app_services["tasks"].detail(approved["id"]).documents[0].error == ""


def test_restart_resumes_pending_and_skips_manual_success(engine, app_services, approved):
    first = worker(app_services, engine)
    first.stopping.set()
    first.run_once()
    assert not app_services["contracts"].calls
    worker(app_services, engine).run_once()
    assert len(app_services["contracts"].calls) == 1
    job = rows(engine, "SELECT * FROM task_contract_jobs")[0]
    app_services["documents"].prepare(job["task_id"], job["purchase_order_id"], USER)
    assert len(app_services["contracts"].calls) == 1


def test_superseded_job_is_not_downloaded(engine, ns, app_services, approved):
    save(ns, engine, bundle([purchase(amounts=("99", "20"))], [customs("870")]))
    approve(app_services, "CD870")
    worker(app_services, engine).run_once()
    jobs = rows(engine, "SELECT * FROM task_contract_jobs ORDER BY id")
    assert [job["status"] for job in jobs] == ["failed", "completed"]
    assert len(app_services["contracts"].calls) == 1


def test_one_failed_contract_does_not_block_others(engine, ns, app_services, monkeypatch):
    save(ns, engine, bundle([purchase("200"), purchase("201")], [customs("870")]))
    approve(app_services, "CD870")
    original = app_services["contracts"].download

    def download(number, *args):
        if number == "SUB-200":
            raise ApiError(502, "隔离合同缺失")
        return original(number, *args)

    monkeypatch.setattr(app_services["contracts"], "download", download)
    worker(app_services, engine).run_once()
    assert [job["status"] for job in rows(engine, "SELECT * FROM task_contract_jobs ORDER BY id")] == [
        "failed",
        "completed",
    ]
    assert task_rows(engine)[0]["status"] == "documents_pending"


def test_file_published_before_interruption_is_recovered(engine, app_services, approved, monkeypatch):
    service = app_services["documents"]

    def interrupted(*args):
        raise SystemExit("模拟文件发布后进程退出")

    with monkeypatch.context() as patch:
        patch.setattr(service, "_archive", interrupted)
        with pytest.raises(SystemExit):
            worker(app_services, engine).run_once()
    first = rows(engine, "SELECT * FROM task_documents")[0]
    assert first["status"] == "pending"
    assert rows(engine, "SELECT status FROM task_contract_jobs")[0]["status"] == "pending"
    worker(app_services, engine).run_once()
    saved = rows(engine, "SELECT * FROM task_documents")[0]
    assert saved["status"] == "archived" and saved["created_at"] == first["created_at"]
    assert len(list(service.archive.root.rglob("*.pdf"))) == 1


def test_application_lifecycle_consumes_queue(context, ns, engine, tmp_path, monkeypatch):
    import importlib
    from dataclasses import replace
    from threading import Event

    from backend.tests.test_task import FakeContracts, FakeWecom
    from fastapi.testclient import TestClient

    module = importlib.import_module("backend.app")
    contracts = FakeContracts()
    finished = Event()
    settings = replace(context.settings, subpo_archive_root=tmp_path)
    monkeypatch.setattr(module, "SourceContracts", lambda client: contracts)
    save(ns, engine, bundle([purchase()], [customs("870")]))
    app = module.create_app(settings, context.ns, engine, wecom=FakeWecom())
    original = app.state.contract_worker.documents._archive

    def archived(*args):
        original(*args)
        finished.set()

    monkeypatch.setattr(app.state.contract_worker.documents, "_archive", archived)
    with TestClient(app) as client:
        headers = {"Origin": settings.origin}
        assert (
            client.post(
                "/api/session",
                headers=headers,
                json={
                    "username": "admin",
                    "password": settings.admin_password,
                },
            ).status_code
            == 200
        )
        item = client.post("/api/review/declarations/query", headers=headers, json={}).json()["groups"][0]
        response = client.post(
            f"/api/review/declarations/{item['id']}/approve",
            headers=headers,
            json={"contentSha256": item["contentSha256"]},
        )
        assert response.status_code == 200
        assert finished.wait(10), "应用后台未自动消费审核生成的合同作业"
        task_id = task_rows(engine)[0]["id"]
        detail = client.get(f"/api/tasks/{task_id}").json()
        assert detail["documents"][0]["status"] == "ready"
        assert detail["task"]["status"] == "notify_pending"
    assert not app.state.contract_worker.thread.is_alive()
