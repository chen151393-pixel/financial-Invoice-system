"""数据库级关联写锁：先串行化关联写，再取得账户锁；外部读取不占事务。"""

import hashlib
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError

from . import named_lock
from .errors import ApiError


@contextmanager
def locked(engine, *account_locks):
    name = hashlib.sha256(f"invoice-ledger:{engine.url.database}".encode()).hexdigest()
    with engine.connect() as connection:
        acquired = []
        try:
            for key in (name, *account_locks):
                with connection.begin():
                    if not named_lock.acquire(connection, key, timeout=10 if key == name else 0):
                        raise ApiError(409, "当前账本有操作正在进行，请刷新后重试")
                acquired.append(key)
            yield connection
        finally:
            try:
                if connection.in_transaction():
                    connection.rollback()
                with connection.begin():
                    for key in reversed(acquired):
                        named_lock.release(connection, key)
            except SQLAlchemyError:
                connection.invalidate()


@contextmanager
def transaction(engine):
    with locked(engine) as connection, connection.begin():
        yield connection
