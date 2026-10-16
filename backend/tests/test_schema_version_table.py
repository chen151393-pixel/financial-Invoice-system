"""迁移版本表的 MySQL 字段扩宽：保留业务数据与既有版本，重复执行不缩短字段。"""

import pytest
from backend.manage import schema_head, upgrade_schema
from backend.tests.test_schema_baseline import purchase_line
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from sqlalchemy import inspect, text

INITIAL_REVISION = "0001_baseline"


@pytest.mark.parametrize("initial_length", [32, 255])
def test_mysql_upgrade_keeps_data_and_existing_version_table(schema_engine, initial_length):
    if schema_engine.dialect.name != "mysql":
        pytest.skip("版本字段长度与扩宽须由真实 MySQL 验证")
    target = schema_engine.url.render_as_string(hide_password=False)
    with schema_engine.begin() as connection:
        order, _ = purchase_line(connection)
        connection.execute(
            text(
                "ALTER TABLE schema_version MODIFY version_num "
                f"VARCHAR({initial_length}) COLLATE utf8mb4_bin NOT NULL"
            )
        )
    upgrade_schema(target)
    upgrade_schema(target)
    with schema_engine.connect() as connection:
        column = inspect(connection).get_columns("schema_version")[0]
        assert column["type"].length == max(initial_length, 128)
        assert column["type"].collation == "utf8mb4_bin"
        assert not column["nullable"]
        assert (
            connection.execute(text("SELECT version_num FROM schema_version")).scalar_one() == schema_head()
        )
        assert (
            connection.execute(
                text("SELECT id FROM source_purchase_orders WHERE id = :id"), {"id": order}
            ).scalar_one()
            == order
        )
