"""持久目录：慢网络隔离、重启、进度、失败保留与凭证隔离；只用隔离 SQLite。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from backend.core.errors import ApiError
from backend.integrations.wecom import WeComError
from backend.modules.task.dao import wecom_directory_dao as dao
from backend.modules.task.service import wecom_directory_service as module
from backend.modules.task.service.wecom_directory_worker import WecomDirectoryWorker
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_supplier_profiles import group


class Adapter:
    def __init__(self):
        self.scope = "corp-a-secret-a-hash"
        self.calls = 0
        self.items = [group("one", "供应商开票群")]
        self.error = None
        self.on_progress = None

    def directory_scope(self):
        return self.scope

    def groups(self, *, progress, expected_scope):
        self.calls += 1
        assert expected_scope == self.scope
        progress("listing", len(self.items), 0, None)
        progress("details", len(self.items), 0, len(self.items))
        if self.on_progress:
            self.on_progress()
        if self.error:
            raise self.error
        progress("details", len(self.items), len(self.items), len(self.items))
        return {"items": self.items, "unavailableCount": 0}


@pytest.fixture
def catalog(engine):
    adapter = Adapter()
    return module.WecomDirectoryService(engine, adapter), adapter


def warm(service):
    service.groups()
    service.run_once()
    return service.groups()


def test_cold_query_and_progress_never_wait_for_network(catalog):
    service, adapter = catalog
    first = service.groups()
    assert first["directoryState"] == "queued" and first["directoryRefreshing"]
    assert not first["directoryHasSnapshot"] and first["directoryTotal"] is None
    assert adapter.calls == 0
    entered, release = Event(), Event()

    def pause():
        entered.set()
        assert release.wait(10)

    adapter.on_progress = pause
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.run_once)
        try:
            assert entered.wait(5)
            progress = service.groups(refresh=True)
            assert progress["directoryState"] == "details"
            assert progress["directoryCompleted"] == 0 and progress["directoryTotal"] == 1
            assert progress["directoryPercent"] == 0
            assert progress["items"] == [] and not progress["directoryHasSnapshot"]
            service.run_once()  # 同服务重入不启动第二次上游读取。
            assert adapter.calls == 1
        finally:
            release.set()
        future.result(timeout=5)
    complete = service.groups()
    assert complete["directoryPercent"] == 100 and complete["directoryHasSnapshot"]
    assert len(complete["items"]) == 1 and not complete["directoryRefreshing"]


def test_restart_and_stale_search_use_database_and_background_refresh(catalog, engine, monkeypatch):
    service, adapter = catalog
    warm(service)
    restart = module.WecomDirectoryService(engine, adapter)
    adapter.error = ApiError(502, "网络中断")
    assert len(restart.groups()["items"]) == 1 and adapter.calls == 1
    later = module.now_utc() + timedelta(seconds=301)
    monkeypatch.setattr(module, "now_utc", lambda: later)
    assert restart.groups()["directoryState"] == "queued"
    assert adapter.calls == 1
    restart.run_once()
    failed = restart.groups()
    assert failed["directoryState"] == "failed" and failed["directoryHasSnapshot"]
    assert failed["directoryRefreshError"] == "网络中断" and len(failed["items"]) == 1
    restart.run_once()
    assert adapter.calls == 2  # 冷却期间查询或后台循环都不能反复拉取。


def test_first_failure_is_not_successful_empty_directory_and_can_retry(catalog):
    service, adapter = catalog
    adapter.error = ApiError(502, "企微不可用")
    failed = warm(service)
    assert failed["directoryState"] == "failed" and not failed["directoryHasSnapshot"]
    assert failed["directoryUpdatedAt"] is None and failed["directoryRefreshError"]
    adapter.error = None
    service.groups(refresh=True)
    service.run_once()
    assert service.groups()["directoryState"] == "ready"


def test_scope_change_during_sync_never_publishes_into_other_scope(catalog, engine):
    service, adapter = catalog
    warm(service)
    adapter.scope = "corp-b-secret-b-hash"
    assert not service.groups()["directoryHasSnapshot"]
    adapter.on_progress = lambda: setattr(adapter, "scope", "corp-c-secret-c-hash")
    service.run_once()
    assert service.groups()["items"] == []
    with engine.connect() as connection:
        old = dao.get(connection, "corp-a-secret-a-hash")
        failed = dao.get(connection, "corp-b-secret-b-hash")
        assert old["has_snapshot"] and not failed["has_snapshot"]
        assert failed["status"] == "failed"


@pytest.mark.parametrize("code", [40001, 48002, 60020])
def test_revoked_credentials_stop_serving_old_directory(catalog, code):
    service, adapter = catalog
    warm(service)
    adapter.error = WeComError(code, "授权已失效")
    service.groups(refresh=True)
    service.run_once()
    result = service.groups()
    assert result["items"] == [] and not result["directoryHasSnapshot"]
    assert result["directoryState"] == "failed"


def test_removed_groups_and_empty_snapshot_are_published_atomically(catalog, engine, monkeypatch):
    service, adapter = catalog
    warm(service)
    adapter.items = [group("two", "新群")]
    original = dao.publish

    def fail_publish(*args):
        original(*args)
        raise ApiError(502, "提交前异常")

    monkeypatch.setattr(dao, "publish", fail_publish)
    service.groups(refresh=True)
    service.run_once()
    assert service.groups()["items"][0]["chatId"] == "one"
    monkeypatch.setattr(dao, "publish", original)
    service.groups(refresh=True)
    service.run_once()
    assert [row["chatId"] for row in service.groups()["items"]] == ["two"]
    adapter.items = []
    service.groups(refresh=True)
    service.run_once()
    empty = service.groups()
    assert empty["items"] == [] and empty["directoryHasSnapshot"] and empty["directoryPercent"] == 100


def test_interrupted_job_is_recovered_and_periodic_worker_uses_same_service(catalog, engine):
    service, adapter = catalog
    service.groups()
    with engine.begin() as connection:
        row = dao.get(connection, adapter.scope)
        dao.change(connection, row["id"], module.now_utc(), status="details", completed=1, total=2)
    restarted = module.WecomDirectoryService(engine, adapter)
    worker = WecomDirectoryWorker(restarted)
    done = Event()
    adapter.on_progress = done.set
    worker.start()
    try:
        assert done.wait(5)
    finally:
        worker.stop()
    assert not worker.thread.is_alive()
    assert restarted.groups()["directoryState"] == "ready"
    assert adapter.calls == 1


def test_background_does_not_create_directory_before_first_query(catalog):
    service, adapter = catalog
    service.run_once()
    assert adapter.calls == 0


def test_existing_group_details_are_updated_without_duplicate_rows(catalog, engine):
    service, adapter = catalog
    warm(service)
    adapter.items = [group("one", "改名后的群", "new_owner")]
    service.groups(refresh=True)
    service.run_once()
    result = service.groups()
    assert len(result["items"]) == 1 and result["items"][0]["groupName"] == "改名后的群"
    assert result["items"][0]["userid"] == "new_owner"


def test_superseded_worker_cannot_publish_or_mark_successor_failed(catalog, engine):
    service, adapter = catalog
    warm(service)

    def replace_worker():
        with engine.begin() as connection:
            row = dao.get(connection, adapter.scope)
            dao.change(connection, row["id"], module.now_utc(), run_token="successor", completed=5, total=8)

    adapter.on_progress = replace_worker
    service.groups(refresh=True)
    service.run_once()
    with engine.connect() as connection:
        row = dao.get(connection, adapter.scope)
        assert row["run_token"] == "successor" and row["status"] == "details"
        assert row["completed"] == 5 and row["total"] == 8 and row["error"] == ""


def test_directory_migration_can_downgrade_and_upgrade_without_touching_other_tables(engine):
    from alembic import command
    from backend.manage import SCHEMA_INI, _config
    from sqlalchemy import inspect

    config = _config(SCHEMA_INI, engine.url.render_as_string(hide_password=False))
    before = set(inspect(engine).get_table_names())
    command.downgrade(config, "0038_source_purchase_line_tax_rate")
    assert set(inspect(engine).get_table_names()) == before - {
        "task_wecom_directories",
        "task_wecom_directory_groups",
        "sync_ns_plans",  # 0040 在没有计划数据时随之回退
    }
    command.upgrade(config, "head")
    assert set(inspect(engine).get_table_names()) == before
