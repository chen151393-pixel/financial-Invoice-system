"""在专用随机 MySQL 库验证账本锁范围：NS 同步读取期间只持账户锁，财务计算和其他写入不被阻塞。

未配置 BUSINESS_MIGRATION_TEST_SERVER_URL 时明确跳过；SQLite 不加命名锁，不能代替本测试。
"""

import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event

import pytest
from backend.app import create_events
from backend.core import named_lock, write_lock
from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.modules.review.dao import calculation_job_dao as jobs
from backend.modules.review.service.calculation_service import now_utc
from backend.modules.review.service.calculation_worker import CalculationWorker
from backend.modules.source.public import DeclarationService
from backend.modules.source.service.storage_service import StorageService
from backend.tests.test_review_calculations_mysql import setup_job
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ACCOUNT, bundle, customs, declaration, purchase
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_sync_optimization import batch as batch
from backend.tests.test_sync_partial_save import page_result
from sqlalchemy.exc import OperationalError


@pytest.fixture
def mysql(schema_engine, monkeypatch):
    if schema_engine.dialect.name != "mysql":
        pytest.skip("账本锁并发必须在 MySQL 验证")
    # 缩短普通写入的账本锁等待：若仍被同步读取阻塞，1 秒内即失败，而不是等满 10 秒。
    monkeypatch.setattr(write_lock, "LEDGER_TIMEOUT", 1)
    return schema_engine


def start_sync(pool, ns, engine):
    """后台启动一次同步保存；collect() 模拟耗时的 NS 读取，直到测试放行。"""
    reading, resume = Event(), Event()
    data = bundle([purchase()], [customs()])

    def collect():
        reading.set()
        assert resume.wait(30), "测试未放行 NS 读取"
        return deepcopy(data)

    service = StorageService(ns, engine, create_events())
    future = pool.submit(service.save, collect, read_relations=False)
    assert reading.wait(10), "同步未进入 NS 读取阶段"
    return future, resume


def test_calculation_and_other_writes_proceed_during_ns_read(mysql, ns, monkeypatch):
    service = setup_job(mysql)
    monkeypatch.setattr(service, "build", lambda account: ([], []))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future, resume = start_sync(pool, ns, mysql)
        try:
            started = time.monotonic()
            # 财务计算认领与发布、柠檬云等其他模块的短事务都需要账本锁，均不应等待同步读取。
            assert service.calculate(service.pending()[0]) is True
            with transaction(mysql) as connection:
                jobs.request(connection, "other-account", now_utc())
            assert time.monotonic() - started < 5
        finally:
            resume.set()
        future.result(timeout=30)
    assert declaration(mysql)["relation_status"] == "complete"


def test_same_account_stays_mutually_exclusive_during_ns_read(mysql, ns):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future, resume = start_sync(pool, ns, mysql)
        try:
            started = time.monotonic()
            # 审核确认持同一账户锁读取来源，同步读取期间应立即拒绝，而不是排队等待。
            with pytest.raises(ApiError) as review, DeclarationService(mysql).locked(ACCOUNT):
                pass
            assert review.value.status == 409
            with pytest.raises(ApiError, match="当前账户已有采购报关保存操作"):
                StorageService(ns, mysql, create_events()).save(
                    lambda: deepcopy(bundle([purchase()], [customs()])), read_relations=False
                )
            assert time.monotonic() - started < 3
        finally:
            resume.set()
        future.result(timeout=30)


def test_sync_commit_waits_for_short_ledger_write_then_saves(mysql, ns):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future, resume = start_sync(pool, ns, mysql)
        with transaction(mysql):
            resume.set()
            time.sleep(1.5)
            assert not future.done(), "同步提交必须等待其他写入释放账本锁"
        future.result(timeout=30)
    assert declaration(mysql)["relation_status"] == "complete"


def test_worker_defers_without_failure_when_ledger_is_busy(mysql, monkeypatch):
    service = setup_job(mysql)
    built = []
    monkeypatch.setattr(service, "build", lambda account: built.append(account))
    with transaction(mysql):
        CalculationWorker(service).run_once()
    with mysql.connect() as connection:
        job = jobs.get(connection, "test-account")
    assert built == [] and job["attempts"] == 0 and job["last_error"] == ""
    assert job["retry_at"] is not None and service.pending() == []


@pytest.mark.parametrize("contended", [False, True])
def test_partial_sync_reacquires_account_lock_after_disconnect(mysql, batch, monkeypatch, contended):
    ns, page, _, _ = batch
    service = StorageService(ns, mysql)
    original = service.commit
    attempts = []
    with mysql.connect() as competitor:

        def commit(connection, bundle, config, account, lock, report):
            attempts.append(bundle["customs"][0][0])
            with connection.begin():
                assert named_lock.owns(connection, lock)
            result = original(connection, bundle, config, account, lock, report)
            if len(attempts) == 2:
                connection.invalidate()
                if contended:
                    with competitor.begin():
                        assert named_lock.acquire(competitor, lock, timeout=2)
                raise OperationalError("", {}, Exception("commit acknowledgement lost"))
            return result

        monkeypatch.setattr(service, "commit", commit)
        try:
            result = service.sync_partial_page("customs-declarations", lambda: page_result(page[:3]))
            assert result["batch"]["canContinue"] is not contended
            assert result["batch"]["counts"]["unknown"] == 1
            assert result["batch"]["counts"]["saved"] == (1 if contended else 2)
            assert len(attempts) == (2 if contended else 3)
        finally:
            # 命名锁不会随事务提交释放，确保测试竞争连接不带锁回池。
            competitor.invalidate()
