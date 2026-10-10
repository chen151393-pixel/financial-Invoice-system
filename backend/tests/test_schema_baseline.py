"""新表结构基线（backend/migrations/0001_baseline）：建表、版本、关键约束与回退。

SQLite 始终运行；提供 BUSINESS_MIGRATION_TEST_SERVER_URL 时，另在随机新建的 MySQL 库上运行同样的检查。
"""

import os
from uuid import uuid4

import pytest
from alembic import command
from backend.core.database import make_engine
from backend.manage import SCHEMA_INI, _config, schema_head, upgrade_schema
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

TABLES = {
    "source_suppliers",
    "source_companies",
    "source_raw_records",
    "source_parent_orders",
    "source_parent_order_lines",
    "source_purchase_orders",
    "source_purchase_order_lines",
    "source_customs_declarations",
    "source_customs_lines",
    "source_customs_purchase_links",
    "review_records",
    "review_lines",
    "task_supplier_groups",
    "task_tasks",
    "task_lines",
    "task_documents",
    "task_notifications",
    "task_events",
    "invoice_raw_records",
    "invoice_headers",
    "invoice_items",
    "matching_allocations",
    "sync_runs",
    "sync_cursors",
}
NOW = "2026-10-10 00:00:00"


def _url(engine):
    return engine.url.render_as_string(hide_password=False)


@pytest.fixture(params=["sqlite", "mysql"])
def schema_engine(request, tmp_path):
    if request.param == "sqlite":
        engine = make_engine(f"sqlite:///{tmp_path / 'schema.sqlite'}")
        upgrade_schema(_url(engine))
        yield engine
        engine.dispose()
        return
    server_url = os.environ.get("BUSINESS_MIGRATION_TEST_SERVER_URL")
    if not server_url:
        pytest.skip("未提供专用MySQL建库连接，未在MySQL上验证新表结构")
    url = make_url(server_url)
    if url.drivername != "mysql+pymysql":
        pytest.fail("迁移集成测试必须使用MySQL")
    # 库名完全由测试生成，销毁时只使用本次生成的标识。
    database = "codex_" + uuid4().hex + "_schema_test"
    server = create_engine(url.set(database=None))
    engine = None
    created = False
    try:
        with server.connect() as connection:
            connection.execute(
                text(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin")
            )
            created = True
        engine = create_engine(url.set(database=database))
        upgrade_schema(_url(engine))
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with server.connect() as connection:
                connection.execute(text(f"DROP DATABASE `{database}`"))
        server.dispose()


def insert(connection, table, **values):
    columns = ", ".join(values)
    params = ", ".join(f":{name}" for name in values)
    return connection.execute(text(f"INSERT INTO {table} ({columns}) VALUES ({params})"), values).lastrowid


def purchase_line(connection):
    order = insert(
        connection,
        "source_purchase_orders",
        ns_account="prod",
        ns_internal_id=uuid4().hex,
        order_no="PO-1",
        synced_at=NOW,
    )
    line = insert(
        connection,
        "source_purchase_order_lines",
        purchase_order_id=order,
        source_line_key=uuid4().hex,
        quantity="10",
        unit="个",
        amount="100.50",
    )
    return order, line


def test_baseline_creates_all_tables_at_head(schema_engine):
    with schema_engine.connect() as connection:
        names = set(inspect(connection).get_table_names())
        assert TABLES <= names
        assert (
            connection.execute(text("SELECT version_num FROM schema_version")).scalar_one() == schema_head()
        )
    # 新迁移链不创建任何旧表名
    assert not {"invoice_lines", "invoices", "purchase_orders", "alembic_version"} & names


def test_timestamps_default_and_decimal_precision_kept(schema_engine):
    with schema_engine.begin() as connection:
        order, line = purchase_line(connection)
        row = connection.execute(
            text("SELECT created_at, updated_at, amount FROM source_purchase_order_lines WHERE id = :id"),
            {"id": line},
        ).one()
    assert row.created_at is not None and row.updated_at is not None
    assert str(row.amount).startswith("100.5")


def test_only_one_active_task_line_per_purchase_line(schema_engine):
    with schema_engine.begin() as connection:
        order, line = purchase_line(connection)
        task_values = dict(review_id=1, ns_account="prod", customs_declaration_id=1)
        first = insert(connection, "task_tasks", group_key="a" * 64, **task_values)
        second = insert(connection, "task_tasks", group_key="b" * 64, **task_values)
        insert(
            connection,
            "task_lines",
            task_id=first,
            review_line_id=1,
            purchase_order_id=order,
            purchase_line_id=line,
        )
    with pytest.raises(IntegrityError):
        with schema_engine.begin() as connection:
            insert(
                connection,
                "task_lines",
                task_id=second,
                review_line_id=2,
                purchase_order_id=order,
                purchase_line_id=line,
            )
    # 旧任务行被替代后，同一子采购行可以生成新的有效任务行。
    with schema_engine.begin() as connection:
        connection.execute(
            text("UPDATE task_lines SET status = 'superseded' WHERE task_id = :id"), {"id": first}
        )
        insert(
            connection,
            "task_lines",
            task_id=second,
            review_line_id=2,
            purchase_order_id=order,
            purchase_line_id=line,
        )
        active = connection.execute(
            text("SELECT COUNT(*) FROM task_lines WHERE purchase_line_id = :id AND status <> 'superseded'"),
            {"id": line},
        ).scalar_one()
    assert active == 1


def test_only_one_active_review_per_declaration(schema_engine):
    values = dict(ns_account="prod", customs_declaration_id=7, content_sha256="c" * 64)
    with schema_engine.begin() as connection:
        insert(connection, "review_records", revision=1, approved_by="admin", approved_at=NOW, **values)
    with pytest.raises(IntegrityError):
        with schema_engine.begin() as connection:
            insert(connection, "review_records", revision=2, approved_by="admin", approved_at=NOW, **values)
    with schema_engine.begin() as connection:
        connection.execute(text("UPDATE review_records SET status = 'superseded' WHERE revision = 1"))
        insert(connection, "review_records", revision=2, approved_by="admin", approved_at=NOW, **values)


def test_matching_pair_unique_while_proposed_or_confirmed(schema_engine):
    base = dict(invoice_id=1, invoice_item_id=5, purchase_line_id=9, quantity="1", amount="1")
    with schema_engine.begin() as connection:
        insert(
            connection,
            "matching_allocations",
            request_id=str(uuid4()),
            proposed_by="system",
            proposed_at=NOW,
            **base,
        )
    with pytest.raises(IntegrityError):
        with schema_engine.begin() as connection:
            insert(
                connection,
                "matching_allocations",
                request_id=str(uuid4()),
                proposed_by="system",
                proposed_at=NOW,
                **base,
            )
    # 驳回后可以重新生成同一对的建议。
    with schema_engine.begin() as connection:
        connection.execute(text("UPDATE matching_allocations SET status = 'rejected'"))
        insert(
            connection,
            "matching_allocations",
            request_id=str(uuid4()),
            proposed_by="system",
            proposed_at=NOW,
            **base,
        )


def test_header_level_link_cannot_be_duplicated(schema_engine):
    with schema_engine.begin() as connection:
        order, _ = purchase_line(connection)
        customs = insert(
            connection, "source_customs_declarations", ns_account="prod", ns_internal_id="CD1", synced_at=NOW
        )
        link = dict(
            customs_declaration_id=customs, purchase_order_id=order, evidence="ns_reference", synced_at=NOW
        )
        insert(connection, "source_customs_purchase_links", **link)
    # 两行级列都为空时，仍按 0 参与唯一性，不能重复插入单头级关系。
    with pytest.raises(IntegrityError):
        with schema_engine.begin() as connection:
            insert(connection, "source_customs_purchase_links", **link)


def test_check_constraint_rejects_unknown_status(schema_engine):
    with pytest.raises(IntegrityError):
        with schema_engine.begin() as connection:
            insert(
                connection,
                "sync_runs",
                source="ns_customs",
                account="prod",
                trigger_type="manual",
                status="done",
                started_by="admin",
                started_at=NOW,
            )


def test_downgrade_removes_only_new_tables(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'schema.sqlite'}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE invoice_lines (id INTEGER PRIMARY KEY)"))
        upgrade_schema(_url(engine))
        command.downgrade(_config(SCHEMA_INI, _url(engine)), "base")
        with engine.connect() as connection:
            names = set(inspect(connection).get_table_names())
        assert not TABLES & names
        assert "invoice_lines" in names  # 同库中的旧表不受影响
    finally:
        engine.dispose()


def test_offline_mysql_ddl_is_generated(capsys):
    upgrade_schema("mysql+pymysql://unused@localhost/unused?charset=utf8mb4", sql=True)
    sql = capsys.readouterr().out
    assert sql.count("CREATE TABLE") == len(TABLES) + 1  # 另含版本表 schema_version
    assert "DEFAULT CURRENT_TIMESTAMP(6)" in sql
    assert "GENERATED ALWAYS AS (CASE WHEN status <> 'superseded' THEN purchase_line_id END) STORED" in sql
    assert "BIGINT UNSIGNED NOT NULL AUTO_INCREMENT" in sql
