"""中文备注迁移：真实 MySQL 验证结构、数据、生成列及降级恢复。"""

import importlib
import re
from io import StringIO
from uuid import uuid4

from alembic import command
from backend.core.schema import schema_metadata
from backend.manage import SCHEMA_INI, _config
from backend.tests.test_schema_baseline import NOW, insert, purchase_line
from backend.tests.test_schema_baseline import TABLES as ALL_TABLES
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from sqlalchemy import inspect, text

TABLES = ALL_TABLES - {
    "sync_lemon_bindings",
    "sync_lemon_runs",
    "task_external_groups",
    "task_group_imports",
}
COMMENT_HEAD = "0015_sync_comments"

INITIAL_REVISION = "0009_matching_ledger_versions"
MODULES = ("source", "review", "task", "invoice", "matching", "sync")


def test_entity_comments_cover_all_columns():
    for module in MODULES:
        importlib.import_module(f"backend.modules.{module}.entity")
    assert set(schema_metadata.tables) == ALL_TABLES - {"sync_runs", "sync_cursors"}
    for table in schema_metadata.tables.values():
        assert table.comment and re.search(r"[\u4e00-\u9fff]", table.comment), table.name
        for column in table.c:
            assert column.comment and re.search(r"[\u4e00-\u9fff]", column.comment), column


def test_offline_comments_only_change_metadata():
    output = StringIO()
    config = _config(SCHEMA_INI, "mysql+pymysql://unused@localhost/unused?charset=utf8mb4")
    config.output_buffer = output
    command.upgrade(config, f"{INITIAL_REVISION}:{COMMENT_HEAD}", sql=True)
    sql = output.getvalue()
    assert sql.count("ALTER TABLE") == 26
    assert sql.count("MODIFY COLUMN") == 422
    assert "AUTO_INCREMENT" in sql
    assert "DEFAULT CURRENT_TIMESTAMP(6)" in sql
    assert "GENERATED ALWAYS AS" in sql
    assert "STORED COMMENT" in sql
    assert "待复核" in sql
    assert not re.search(r"\b(DROP|TRUNCATE|DELETE|INSERT|CREATE TABLE)\b", sql)
    assert sql.count("UPDATE ") == 6  # 只推进六步 schema_version。
    assert sql.count("UPDATE schema_version ") == 6


def snapshot(engine):
    inspector = inspect(engine)
    structures, data, comments = {}, {}, {}
    with engine.connect() as connection:
        for name in sorted(TABLES | {"legacy_comment_sentinel"}):
            columns = inspector.get_columns(name)
            comments[name] = {c["name"]: c.pop("comment", None) for c in columns}
            structures[name] = {
                "columns": repr(columns),
                "pk": inspector.get_pk_constraint(name),
                "indexes": inspector.get_indexes(name),
                "foreign_keys": inspector.get_foreign_keys(name),
                "checks": inspector.get_check_constraints(name),
            }
            if engine.dialect.name == "mysql":
                comments[name]["__table__"] = inspector.get_table_comment(name)["text"]
            data[name] = connection.execute(text(f"SELECT * FROM `{name}` ORDER BY 1")).fetchall()
    return structures, data, comments


def seed(engine):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE legacy_comment_sentinel (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO legacy_comment_sentinel VALUES (71)"))
        order, line = purchase_line(connection)
        connection.execute(
            text(
                "UPDATE source_purchase_order_lines SET quantity=123456789.12345678, amount=123456789.123456"
            )
        )
        review = insert(
            connection,
            "review_records",
            ns_account="prod",
            customs_declaration_id=1,
            revision=1,
            content_sha256="a" * 64,
            approved_by="测试用户",
            approved_at=NOW,
        )
        task = insert(
            connection,
            "task_tasks",
            review_id=review,
            ns_account="prod",
            customs_declaration_id=1,
            group_key="b" * 64,
        )
        insert(
            connection,
            "task_lines",
            task_id=task,
            review_line_id=1,
            purchase_order_id=order,
            purchase_line_id=line,
            expected_quantity="123456789.12345678",
        )
        insert(
            connection,
            "matching_allocations",
            invoice_id=1,
            invoice_item_id=2,
            purchase_line_id=line,
            quantity="1.00000001",
            amount="1.000001",
            proposed_by="测试用户",
            proposed_at=NOW,
            request_id=str(uuid4()),
        )


def assert_mysql_comments(engine, comments):
    if engine.dialect.name != "mysql":
        return
    assert sum(len(comments[name]) - 1 for name in TABLES) == 422
    for name in TABLES:
        assert all(value and re.search(r"[\u4e00-\u9fff]", value) for value in comments[name].values()), name
    for module in MODULES:
        importlib.import_module(f"backend.modules.{module}.entity")
    for name, table in schema_metadata.tables.items():
        if name not in TABLES:
            continue
        assert comments[name]["__table__"] == table.comment
        for column in table.c:
            assert comments[name][column.name] == column.comment, (name, column.name)


def test_comment_upgrade_and_downgrade_preserve_structure_and_data(schema_engine):
    seed(schema_engine)
    url = schema_engine.url.render_as_string(hide_password=False)
    before_structure, before_data, before_comments = snapshot(schema_engine)
    command.upgrade(_config(SCHEMA_INI, url), COMMENT_HEAD)
    after_structure, after_data, after_comments = snapshot(schema_engine)
    assert after_structure == before_structure
    assert after_data == before_data
    assert after_comments["legacy_comment_sentinel"] == before_comments["legacy_comment_sentinel"]
    assert_mysql_comments(schema_engine, after_comments)
    command.downgrade(_config(SCHEMA_INI, url), INITIAL_REVISION)
    assert snapshot(schema_engine) == (before_structure, before_data, before_comments)
    command.upgrade(_config(SCHEMA_INI, url), COMMENT_HEAD)
    assert snapshot(schema_engine) == (after_structure, after_data, after_comments)
