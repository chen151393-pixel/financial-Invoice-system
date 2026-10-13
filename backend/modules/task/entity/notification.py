"""供应商开票通知：每次保存一个版本。"""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Table, Text, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

notifications = Table(
    "task_notifications",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("task_id", ID, ForeignKey("task_tasks.id", name="fk_task_notification_task"), nullable=False),
    Column("version", Integer, nullable=False),
    Column("channel", String(24), nullable=False, server_default="manual"),
    Column("chat_id", String(190)),
    Column("recipient_name", String(200)),
    Column("content", Text, nullable=False),
    Column("status", String(24), nullable=False, server_default="draft"),
    Column("sent_by", String(200)),
    Column("sent_at", TIMESTAMP),
    Column("channel_message_id", String(190), comment="企微回执，接入自动发送后填写"),
    Column("created_by", String(200), nullable=False),
    *timestamps(),
    Column("sender_name", String(100), comment="负责发送的员工"),
    Column("note", String(500), comment="人工登记发送说明"),
    UniqueConstraint("task_id", "version", name="uq_task_notification_version"),
    CheckConstraint("channel IN ('manual','wecom')", name="ck_task_notification_channel"),
    CheckConstraint("status IN ('draft','sent','failed')", name="ck_task_notification_status"),
    comment="供应商开票通知：每次保存一个版本",
    **table_options,
)
