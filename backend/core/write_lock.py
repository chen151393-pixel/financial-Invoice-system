"""数据库级关联写锁：先串行化关联写，再取得账户锁；外部读取不占事务。

账本锁只覆盖写库短事务。需要在"读取外部数据 → 保存"期间保持互斥的同步，读取时只持账户锁
（locked(..., ledger=False)），提交前再用 hold_ledger() 在同一连接上短暂取得账本锁。
两种加锁顺序相反，但账户锁始终不等待（超时 0），不会形成互相等待。
"""

import hashlib
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError

from . import named_lock
from .errors import ApiError

LEDGER_TIMEOUT = 10
BUSY_CODE = "ledger_busy"


def ledger_name(engine):
    return hashlib.sha256(f"invoice-ledger:{engine.url.database}".encode()).hexdigest()


def _busy():
    return ApiError(409, "当前账本有操作正在进行，请刷新后重试", code=BUSY_CODE)


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
        yield connection
    finally:
        _release(connection, [name])


@contextmanager
def transaction(engine):
    with locked(engine) as connection, connection.begin():
        yield connection
