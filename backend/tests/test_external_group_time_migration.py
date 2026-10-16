"""创建时间放宽迁移保留原日期，并允许缺省；真实 MySQL 由专用连接运行。"""

from backend.manage import upgrade_schema
from backend.tests.test_schema_baseline import insert
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from sqlalchemy import inspect, text

INITIAL_REVISION = "0018_sync_lemon_runs"


def test_optional_time_migration_preserves_existing_groups(schema_engine):
    with schema_engine.begin() as connection:
        insert(
            connection,
            "task_external_groups",
            chat_id="wr_time",
            group_name="日期保留群",
            owner_name="群主",
            owner_userid="owner",
            member_count=3,
            department="采购",
            group_created_at="2026-10-16 04:36:00",
            filename="groups.xlsx",
            version=1,
            updated_by="user:admin",
        )
    upgrade_schema(schema_engine.url.render_as_string(hide_password=False))
    column = next(
        c
        for c in inspect(schema_engine).get_columns("task_external_groups")
        if c["name"] == "group_created_at"
    )
    assert column["nullable"]
    with schema_engine.begin() as connection:
        assert str(
            connection.execute(text("SELECT group_created_at FROM task_external_groups")).scalar()
        ).startswith("2026-10-16 04:36:00")
        connection.execute(text("UPDATE task_external_groups SET group_created_at = NULL"))
        assert connection.execute(text("SELECT group_created_at FROM task_external_groups")).scalar() is None
        assert connection.execute(text("SELECT chat_id FROM task_external_groups")).scalar() == "wr_time"
