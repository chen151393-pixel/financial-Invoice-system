import os
from io import StringIO

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from backend.config import ROOT, load_settings
from backend.database import make_engine, metadata, target_locks
from backend.manage import upgrade
from backend.netsuite import ApiError
from backend.tests.conftest import FakeNS
from backend.workflow import Workflow
from sqlalchemy import inspect, select
from sqlalchemy.engine import make_url


def test_mysql_8_ddl_portable_locks_charset_and_text_capacity():
    output = StringIO()
    config = Config(str(ROOT / "backend" / "alembic.ini"), output_buffer=output)
    config.attributes["database_url"] = "mysql+pymysql://unused@localhost/test?charset=utf8mb4"
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "ENGINE=InnoDB" in sql and "utf8mb4" in sql
    assert "PRIMARY KEY (account, target)" in sql and "FOREIGN KEY(preview_id)" in sql
    assert "snapshot LONGTEXT" in sql and "expires BIGINT" in sql
    assert "WHERE state" not in sql and "PRAGMA" not in sql


def test_migrations_match_models_and_are_repeatable(context):
    upgrade(context.settings.database_url)
    with context.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), metadata) == []


@pytest.mark.parametrize(
    "values",
    [
        {"NETSUITE_PRIVATE_KEY_PATH": "public/private.pem"},
        {"NETSUITE_PRIVATE_KEY_PATH": "web/private.pem"},
        {"DATABASE_URL": "sqlite:///./dist/secret.sqlite"},
        {"DATABASE_URL": "postgresql://user:secret@localhost/test"},
        {"APP_ORIGIN": "http://example.com"},
        {"APP_ORIGIN": "https://example.com/"},
        {"NETSUITE_WRITE_FIELDS": "[]"},
        {"NETSUITE_WRITE_ENABLED": "yes"},
        {"DATABASE_PATH": "./data/ns.sqlite"},
    ],
)
def test_bad_config_fails_closed(values):
    with pytest.raises(ValueError):
        load_settings(values)


def test_mysql_url_credentials_hidden_and_charset_configured():
    c = load_settings({"DATABASE_URL": "mysql+pymysql://user:secret%40password@127.0.0.1:3306/ns_invoice"})
    assert make_url(c.database_url).query["charset"] == "utf8mb4"
    assert make_url(c.database_url).password == "secret@password"
    assert "secret" not in repr(c)


@pytest.mark.skipif(not os.environ.get("MYSQL_TEST_URL"), reason="需要专用空 MySQL 8.0 测试库 MYSQL_TEST_URL")
def test_live_mysql_8_migration_transactions_and_unknown_lock(env):
    # Opt-in integration test. Never use or clean up an existing business database.
    c = load_settings({**env, "DATABASE_URL": os.environ["MYSQL_TEST_URL"]})
    url = make_url(c.database_url)
    assert url.drivername == "mysql+pymysql" and url.database.startswith("ns_test_")
    engine = make_engine(c.database_url)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT VERSION()").scalar().startswith("8.0.")
            assert inspect(connection).get_table_names() == [], "MYSQL_TEST_URL 必须使用空测试库"
        upgrade(c.database_url)
        ns = FakeNS(c)
        workflow = Workflow(c, ns, engine)
        body = {"type": "vendorBill", "id": "1", "operation": "update", "payload": {"memo": "中文校对 ✓"}}
        p = workflow.preview(body, "owner")
        assert workflow.execute(p["id"], "owner")["state"] == "succeeded"
        assert workflow.execute(p["id"], "owner")["state"] == "succeeded"
        assert len(ns.writes) == 1
        ns.fail_write = True
        q = workflow.preview(body, "owner")
        assert workflow.execute(q["id"], "owner")["state"] == "unknown"
        r = workflow.preview(body, "owner")
        with pytest.raises(ApiError):
            workflow.execute(r["id"], "owner")
        with engine.connect() as connection:
            assert connection.execute(select(target_locks)).first() is not None
    finally:
        engine.dispose()
    # Keep this isolated test schema for inspection; it is never dropped automatically.
