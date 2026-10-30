"""锁域细化：模块写锁不等待账本锁、同模块仍串行；任务操作先锁任务行再复核开票依据；
行锁等待超时与死锁转为 409。

并发用例只在专用随机 MySQL 库执行（BUSINESS_MIGRATION_TEST_SERVER_URL），未配置时明确跳过；
SQLite 不加命名锁，只能验证取锁名称与错误转换。
"""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

import pytest
from backend.app import create_events
from backend.core import named_lock, write_lock
from backend.core.database import make_engine
from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.modules.review.dao import purchase_basis_dao
from backend.modules.review.public import PurchaseBasisInvalidated
from backend.modules.task.dao import task_line_dao
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_task import USER, draft
from backend.tests.test_task import app_services as app_services
from backend.tests.test_task import approved as approved
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


@pytest.fixture
def short_wait(monkeypatch):
    # 若仍被占用，1 秒内即失败，而不是等满 10 秒。
    monkeypatch.setattr(write_lock, "LEDGER_TIMEOUT", 1)


@pytest.fixture
def sqlite(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'scope.sqlite'}")
    yield engine
    engine.dispose()


def test_scoped_transaction_takes_only_its_module_lock(sqlite, monkeypatch):
    names = []
    monkeypatch.setattr(named_lock, "acquire", lambda connection, name, timeout=0: names.append(name) or True)
    with transaction(sqlite, "task"):
        pass
    with transaction(sqlite):
        pass
    assert names == [write_lock.scope_name(sqlite, "task"), write_lock.ledger_name(sqlite)]
    assert write_lock.scope_name(sqlite, "task") != write_lock.scope_name(sqlite, "identity")


class DriverError(Exception):
    pass


@pytest.mark.parametrize("scope", [None, "task"])
@pytest.mark.parametrize("code", [1205, 1213])
def test_lock_wait_timeout_and_deadlock_become_409(sqlite, scope, code):
    with pytest.raises(ApiError) as conflict, transaction(sqlite, scope):
        raise OperationalError("UPDATE", {}, DriverError(code, "锁冲突"))
    assert conflict.value.status == 409 and conflict.value.code == write_lock.CONFLICT_CODE
    # 其他数据库错误保持原样，由调用方按“结果不明 / 保存失败”处理。
    with pytest.raises(OperationalError), transaction(sqlite, scope):
        raise OperationalError("UPDATE", {}, DriverError(2013, "连接中断"))


def test_module_writes_proceed_while_ledger_is_held(engine, short_wait, app_services, approved):
    with transaction(engine):
        started = time.monotonic()
        # 账本被长写入占用时，任务通知与身份模块写入不再排队。
        saved = app_services["notifications"].save_draft(approved["id"], draft(), USER)
        with transaction(engine, "identity") as connection:
            connection.exec_driver_sql("SELECT 1")
        assert time.monotonic() - started < 1
    assert saved.notification.revision == 1


def test_same_scope_and_ledger_stay_mutually_exclusive(engine, short_wait):
    with transaction(engine, "task"):
        with pytest.raises(ApiError) as busy, transaction(engine, "task"):
            pass
        assert busy.value.status == 409 and busy.value.code == write_lock.SCOPE_BUSY_CODE
        with transaction(engine, "identity"), transaction(engine):
            pass
    with transaction(engine):
        with pytest.raises(ApiError) as busy, transaction(engine):
            pass
        assert busy.value.code == write_lock.BUSY_CODE


def test_task_write_rechecks_basis_after_waiting_for_chain(engine, app_services, approved):
    """事件链已改依据、持任务行锁未提交时，通知保存须等其提交，并按新依据拒绝。"""
    task_id = approved["id"]
    with engine.connect() as connection:
        line_ids = [row["purchase_line_id"] for row in task_line_dao.by_tasks(connection, [task_id])]
        basis_ids = [b["id"] for b in purchase_basis_dao.current(connection, line_ids).values()]
    events = create_events()
    locked, release = Event(), Event()

    def invalidate():
        with transaction(engine) as connection:
            purchase_basis_dao.set_status(
                connection, basis_ids, "review_required", datetime.now(UTC).replace(tzinfo=None)
            )
            # 真实订阅链：matching 失效 → 发布收票汇总 → task 锁任务行重算进度。
            events.publish(connection, PurchaseBasisInvalidated(tuple(line_ids), "测试来源变化"))
            locked.set()
            assert release.wait(30), "测试未放行事件链提交"

    with ThreadPoolExecutor(max_workers=2) as pool:
        chain = pool.submit(invalidate)
        assert locked.wait(20), "事件链未进入持锁阶段"
        saving = pool.submit(app_services["notifications"].save_draft, task_id, draft(), USER)
        time.sleep(1)
        assert not saving.done(), "通知保存应等待事件链释放任务行锁"
        release.set()
        chain.result(timeout=30)
        with pytest.raises(ApiError, match="采购来源或开票依据已变化"):
            saving.result(timeout=30)


def test_mysql_deadlock_is_reported_as_conflict(engine):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE lock_probe (id INT PRIMARY KEY, hits INT NOT NULL)"))
        connection.execute(text("INSERT INTO lock_probe VALUES (1, 0), (2, 0)"))
    first_held, second_held = Event(), Event()

    def touch(connection, row):
        connection.execute(text("UPDATE lock_probe SET hits = hits + 1 WHERE id = :id"), {"id": row})

    def crossing(scope, first, second, mine, other):
        # 两个事务交叉锁两行，必有一方被 MySQL 判定死锁并整体回滚。
        with transaction(engine, scope) as connection:
            touch(connection, first)
            mine.set()
            assert other.wait(20)
            touch(connection, second)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            pool.submit(crossing, "probe-a", 1, 2, first_held, second_held),
            pool.submit(crossing, "probe-b", 2, 1, second_held, first_held),
        ]
        errors = [future.exception(timeout=30) for future in results]
    failed = [error for error in errors if error is not None]
    assert len(failed) == 1 and isinstance(failed[0], ApiError)
    assert failed[0].code == write_lock.CONFLICT_CODE
    with engine.connect() as connection:
        hits = connection.execute(text("SELECT SUM(hits) FROM lock_probe")).scalar()
    assert hits == 2, "被判死锁的一方已整体回滚，只保留另一方的两次更新"
