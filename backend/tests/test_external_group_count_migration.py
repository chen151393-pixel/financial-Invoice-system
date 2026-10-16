"""群人数放宽迁移保留已有计数；MySQL 验证需专用连接。"""

from backend.manage import upgrade_schema
from backend.tests.test_schema_baseline import insert
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from sqlalchemy import inspect, text

INITIAL_REVISION = "0019_task_optional_group_time"


def test_optional_count_migration_preserves_existing_groups(schema_engine):
    with schema_engine.begin() as connection:
        insert(
            connection,
            "task_external_groups",
            chat_id="wr_count",
            group_name="人数保留群",
            owner_name="群主",
            owner_userid="owner",
            member_count=8,
            department="采购",
            filename="groups.xlsx",
            version=1,
            updated_by="user:admin",
        )
    upgrade_schema(schema_engine.url.render_as_string(hide_password=False))
    column = next(
        c for c in inspect(schema_engine).get_columns("task_external_groups") if c["name"] == "member_count"
    )
    assert column["nullable"]
    with schema_engine.begin() as connection:
        assert connection.execute(text("SELECT member_count FROM task_external_groups")).scalar() == 8
        connection.execute(text("UPDATE task_external_groups SET member_count = NULL"))
        assert connection.execute(text("SELECT member_count FROM task_external_groups")).scalar() is None
        assert connection.execute(text("SELECT chat_id FROM task_external_groups")).scalar() == "wr_count"
