"""独立数据库验证绑定状态竞争；MySQL 未配置时明确跳过。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from backend.modules.sync.dao import lemon_binding_dao as dao
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from sqlalchemy import inspect


def test_binding_migration_and_conditional_transition(schema_engine):
    columns = {column["name"] for column in inspect(schema_engine).get_columns("sync_lemon_bindings")}
    assert not {"password", "code", "access_token", "refresh_token"} & columns
    with schema_engine.begin() as connection:
        dao.prepare(connection, "scope", "user:admin", "13800000001")
    with schema_engine.begin() as connection:
        assert not dao.transition(connection, "scope", ("unbound",), "binding", "13900000000")
        assert dao.transition(connection, "scope", ("unbound",), "binding", "13800000001")
    with schema_engine.begin() as connection:
        assert not dao.transition(connection, "scope", ("unbound",), "binding")
        assert dao.get(connection, "scope")["status"] == "binding"


def test_mysql_only_one_submit_claim(schema_engine):
    if schema_engine.dialect.name != "mysql":
        pytest.skip("并发状态抢占必须在 MySQL 验证")
    with schema_engine.begin() as connection:
        dao.prepare(connection, "concurrent", "user:admin", "13800000001")
    barrier = Barrier(2)

    def claim():
        barrier.wait(timeout=5)
        with schema_engine.begin() as connection:
            return dao.transition(connection, "concurrent", ("unbound",), "binding", "13800000001")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sorted(results) == [False, True]
