"""供应商开票通知：每次保存一个版本。"""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Table, Text, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

notifications = Table(
    "task_notifications",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "task_id",
        ID,
        ForeignKey("task_tasks.id", name="fk_task_notification_task"),
        comment="开票任务 ID，指向 task_tasks.id",
        nullable=False,
    ),
    Column("version", Integer, comment="同一任务的通知内容版本号", nullable=False),
    Column(
        "channel",
        String(24),
        comment="通知渠道：manual 人工登记；wecom 企业微信自动发送预留",
        nullable=False,
        server_default="manual",
    ),
    Column("chat_id", String(190), comment="企业微信群 ID；不能把群名称当作群身份"),
    Column("recipient_name", String(200), comment="通知接收对象或群的显示名称快照"),
    Column("content", Text, comment="本版本开票通知正文", nullable=False),
    Column(
        "status",
        String(24),
        comment="通知状态：draft 草稿；sent 已登记发送；failed 失败",
        nullable=False,
        server_default="draft",
    ),
    Column("sent_by", String(200), comment="登记发送的认证操作者；与实际发送员工 sender_name 分开"),
    Column("sent_at", TIMESTAMP, comment="登记的实际发送时间，统一保存 UTC"),
    Column("channel_message_id", String(190), comment="渠道消息回执 ID；企业微信自动发送尚未接入"),
    Column("created_by", String(200), comment="创建通知版本的认证操作者", nullable=False),
    *timestamps(),
    Column("sender_name", String(100), comment="负责实际发送的员工姓名"),
    Column("note", String(500), comment="人工备注或登记说明，具体长度见类型"),
    UniqueConstraint("task_id", "version", name="uq_task_notification_version"),
    CheckConstraint("channel IN ('manual','wecom')", name="ck_task_notification_channel"),
    CheckConstraint("status IN ('draft','sent','failed')", name="ck_task_notification_status"),
    comment="供应商开票通知：每次保存一个版本",
    **table_options,
)
