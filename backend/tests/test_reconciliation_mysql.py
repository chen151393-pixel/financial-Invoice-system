"""仅在随机新建的MySQL应用测试库验证迁移、行锁、并发和审计。"""

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from backend.core.config import load_settings
from backend.database import make_engine
from backend.manage import upgrade
from backend.modules.business.pl_script_service import PlScriptService
from backend.modules.reconciliation.service import ReconciliationService
from backend.modules.reconciliation.task_entity import tasks
from backend.tests.conftest import FakeNS
from backend.tests.test_reconciliation import concurrent_approval, source_result
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url


@pytest.fixture
def mysql_finance_context(env):
    server_url = os.environ.get("FINANCE_TEST_SERVER_URL")
    if not server_url:
        pytest.skip("未配置独立MySQL建库连接，不以SQLite替代并发验证")
    url = make_url(server_url)
    assert url.drivername == "mysql+pymysql"
    database = "codex_" + uuid4().hex + "_finance_test"
    server = create_engine(url.set(database=None))
    engine = None
    created = False
    try:
        with server.connect() as connection:
            connection.execute(
                text(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin")
            )
            created = True
        database_url = url.set(database=database).render_as_string(hide_password=False)
        settings = load_settings({**env, "DATABASE_URL": database_url})
        upgrade(database_url)
        engine = make_engine(database_url)
        assert {"finance_reviews", "finance_review_snapshots", "finance_review_audit"} <= set(
            inspect(engine).get_table_names()
        )
        yield SimpleNamespace(settings=settings, engine=engine)
    finally:
        if engine:
            engine.dispose()
        if created:
            # 唯一销毁目标为上方本次创建的随机测试库，绝不使用配置中的业务库名。
            with server.connect() as connection:
                connection.execute(text(f"DROP DATABASE `{database}`"))
        server.dispose()


def test_mysql_concurrent_approval_is_single_audited_transaction(mysql_finance_context):
    context = mysql_finance_context
    ns = FakeNS(context.settings)

    def query(criteria):
        response = source_result(context.settings.account)
        response["query"] = criteria
        return response

    ns.pl_script_query = query
    context.service = ReconciliationService(context.settings, PlScriptService(ns), context.engine)
    concurrent_approval(context)
    with context.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(tasks)) == 1
    assert ns.writes == []
