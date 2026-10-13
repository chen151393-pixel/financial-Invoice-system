"""任务状态历史，只追加。"""

from sqlalchemy import Column, ForeignKey, Index, String, Table

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

events = Table(
    "task_events",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("task_id", ID, ForeignKey("task_tasks.id", name="fk_task_event_task"), nullable=False),
    Column("from_status", String(24)),
    Column("to_status", String(24), nullable=False),
    Column("reason", String(300)),
    Column("actor", String(200), nullable=False, comment="操作人或 system"),
    Column("occurred_at", TIMESTAMP, nullable=False),
    *timestamps(),
    Index("ix_task_event_task", "task_id", "occurred_at"),
    comment="任务状态历史，只追加",
    **table_options,
)
