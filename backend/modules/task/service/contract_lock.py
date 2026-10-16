"""合同下载互斥：覆盖 NS 读取及归档，但不持有数据库事务。"""

import hashlib
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError

from backend.core import named_lock

BUSY_REASON = "此合同正在下载归档，请稍后刷新或重试"


@contextmanager
def contract_lock(engine, key):
    name = hashlib.sha256(f"contract:{engine.url.database}:{key}".encode()).hexdigest()
    with engine.connect() as connection:
        acquired = False
        try:
            with connection.begin():
                acquired = named_lock.acquire(connection, name)
            yield acquired
        finally:
            if acquired:
                try:
                    with connection.begin():
                        named_lock.release(connection, name)
                except SQLAlchemyError:
                    connection.invalidate()
