"""并发结论只来自专用 MySQL 隔离库；未配置时明确跳过。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.modules.writeback.entity import audit, invoice_guards, plans, tasks
from backend.modules.writeback.service.queue_service import enqueue
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import world as world
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_writeback_prepare import USER, confirmation, query
from backend.tests.test_writeback_prepare import prepared as prepared
from sqlalchemy import select


@pytest.fixture
def engine(schema_engine):
    if schema_engine.dialect.name != "mysql":
        pytest.skip("本用例只验证 MySQL 并发，不用 SQLite 代替")
    return schema_engine


def test_mysql_concurrent_enqueue_and_confirm(engine, prepared):
    with transaction(engine) as connection:
        for table in (invoice_guards, audit, plans, tasks):
            connection.execute(table.delete())
    barrier = Barrier(2)

    def add():
        barrier.wait(timeout=10)
        with transaction(engine) as connection:
            return enqueue(connection, prepared.invoice_id, USER)["taskId"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: add(), range(2)))
    assert ids[0] == ids[1]
    prepared.task_id = int(ids[0])
    task = query(prepared)
    bodies = [confirmation(task), confirmation(task)]
    barrier = Barrier(2)

    def confirm(body):
        barrier.wait(timeout=10)
        try:
            return prepared.service.confirm(prepared.task_id, body, USER)["state"]
        except ApiError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(confirm, bodies))
    assert set(outcomes) == {"ready", 409}
    with engine.connect() as connection:
        assert len(connection.execute(select(plans)).all()) == 1
