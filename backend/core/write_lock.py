"""数据库级关联写锁：先串行化关联写，再取得账户锁；外部读取不占事务。

账本锁只覆盖写库短事务。需要在"读取外部数据 → 保存"期间保持互斥的同步，读取时只持账户锁
（locked(..., ledger=False)），提交前再用 hold_ledger() 在同一连接上短暂取得账本锁。
两种加锁顺序相反，但账户锁始终不等待（超时 0），不会形成互相等待。

模块写锁（transaction(engine, scope="模块名")）：不发布事件、不写入或锁定事件链会插入的行、
锁行顺序与事件链一致（先任务后子记录）的写入，只与本模块同类写入串行，不再等待账本锁；
跨事件链的一致性由行锁与版本校验保证。一个连接只持账本锁或模块写锁之一，不会互相等待。
"""

import hashlib
from contextlib import contextmanager

from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from . import named_lock
from .errors import ApiError

LEDGER_TIMEOUT = 10
BUSY_CODE = "ledger_busy"
SCOPE_BUSY_CODE = "write_busy"
CONFLICT_CODE = "lock_conflict"
# MySQL 行锁等待超时与死锁：事务已整体回滚，结果确定，可提示用户稍后重试。
LOCK_CONFLICTS = (1205, 1213)


def ledger_name(engine):
    return hashlib.sha256(f"invoice-ledger:{engine.url.database}".encode()).hexdigest()


def scope_name(engine, scope):
    return hashlib.sha256(f"invoice-write:{scope}:{engine.url.database}".encode()).hexdigest()


def _busy():
    return ApiError(409, "当前账本有操作正在进行，请刷新后重试", code=BUSY_CODE)


def _scope_busy():
    return ApiError(409, "当前有同类操作正在进行，请稍后重试", code=SCOPE_BUSY_CODE)


def _conflict():
    return ApiError(409, "数据正被其他操作处理，未保存，请稍后重试", code=CONFLICT_CODE)


def _lock_conflict(error):
    args = getattr(error.orig, "args", ())
    return bool(args) and args[0] in LOCK_CONFLICTS


@contextmanager
def _conflicts_as_409():
    try:
        yield
    except DBAPIError as error:
        if _lock_conflict(error):
            raise _conflict() from None
        raise


def _release(connection, keys):
    try:
        if connection.in_transaction():
            connection.rollback()
        with connection.begin():
            for key in reversed(keys):
                named_lock.release(connection, key)
    except SQLAlchemyError:
        connection.invalidate()


@contextmanager
def locked(engine, *account_locks, ledger=True):
    keys = ((ledger_name(engine),) if ledger else ()) + account_locks
    with engine.connect() as connection:
        acquired = []
        try:
            for index, key in enumerate(keys):
                with connection.begin():
                    timeout = LEDGER_TIMEOUT if ledger and index == 0 else 0
                    if not named_lock.acquire(connection, key, timeout=timeout):
                        raise _busy()
                acquired.append(key)
            with _conflicts_as_409():
                yield connection
        finally:
            _release(connection, acquired)


@contextmanager
def hold_ledger(connection, timeout=LEDGER_TIMEOUT):
    """在已持账户锁的连接上短暂取得账本锁，退出即释放；释放失败丢弃连接，由 MySQL 回收全部锁。"""
    name = ledger_name(connection.engine)
    with connection.begin():
        acquired = named_lock.acquire(connection, name, timeout=timeout)
    if not acquired:
        raise _busy()
    try:
        with _conflicts_as_409():
            yield connection
    finally:
        _release(connection, [name])


@contextmanager
def _scoped(engine, scope):
    name = scope_name(engine, scope)
    with engine.connect() as connection:
        with connection.begin():
            acquired = named_lock.acquire(connection, name, timeout=LEDGER_TIMEOUT)
        if not acquired:
            raise _scope_busy()
        try:
            with _conflicts_as_409():
                yield connection
        finally:
            _release(connection, [name])


@contextmanager
def transaction(engine, scope=None):
    """scope 为空取全局账本锁（参与跨模块事件链的写入）；给出模块名时只取该模块写锁。"""
    hold = locked(engine) if scope is None else _scoped(engine, scope)
    with hold as connection, connection.begin():
        yield connection
