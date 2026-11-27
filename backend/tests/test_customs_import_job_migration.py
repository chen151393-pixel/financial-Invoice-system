"""恢复已执行的 0057 原版迁移：升级保留业务数据，重复升级幂等，有作业时禁止降级。"""

import pytest
from alembic import command
from backend.manage import SCHEMA_INI, _config, upgrade_schema
from backend.tests.test_schema_baseline import purchase_line
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from sqlalchemy import inspect, text

INITIAL_REVISION = "0056_review_customs_difference_kinds"
RESTORED_REVISION = "0057_review_customs_import_jobs"


@pytest.mark.parametrize("status", ["pending", "running", "completed", "failed"])
def test_restored_migration_is_idempotent_and_preserves_jobs(schema_engine, status):
    target = schema_engine.url.render_as_string(hide_password=False)
    with schema_engine.begin() as connection:
        order_id, _ = purchase_line(connection)
    upgrade_schema(target)
    upgrade_schema(target)
    with schema_engine.begin() as connection:
        assert "review_customs_import_jobs" in inspect(connection).get_table_names()
        assert (
            connection.execute(text("SELECT version_num FROM schema_version")).scalar_one()
            == RESTORED_REVISION
        )
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM source_purchase_orders WHERE id=:id"), {"id": order_id}
            ).scalar_one()
            == 1
        )
        connection.execute(
            text(
                "INSERT INTO review_customs_import_jobs (file_name,upload_key,actor,status) "
                "VALUES (:file,:key,:actor,:status)"
            ),
            {"file": "迁移验证.xlsx", "key": "a" * 32, "actor": "admin", "status": status},
        )
    with pytest.raises(RuntimeError, match="不能自动删除导入历史"):
        command.downgrade(_config(SCHEMA_INI, target), INITIAL_REVISION)
    with schema_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM schema_version")).scalar_one()
            == RESTORED_REVISION
        )
        assert (
            connection.execute(text("SELECT status FROM review_customs_import_jobs")).scalar_one() == status
        )
