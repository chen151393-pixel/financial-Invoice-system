"""企微发送台账与群守卫；发送证据不得通过降级删除。"""

from alembic import op
from backend.core.schema import ID, TIMESTAMP, identifier, table_options, timestamps
from sqlalchemy import JSON, CheckConstraint, Column, ForeignKey, String, UniqueConstraint

revision = "0022_task_notifications"
down_revision = "0021_task_contract_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_notification_deliveries",
        Column("id", ID, primary_key=True, autoincrement=True, comment="发送执行主键"),
        Column(
            "task_id",
            ID,
            ForeignKey("task_tasks.id", name="fk_task_delivery_task"),
            nullable=False,
            comment="所属任务",
        ),
        Column(
            "notification_id",
            ID,
            ForeignKey("task_notifications.id", name="fk_task_delivery_notification"),
            nullable=False,
            comment="通知版本",
        ),
        Column("request_id", identifier(64), nullable=False, comment="客户端幂等编号"),
        Column("request_sha256", String(64), nullable=False, comment="提交请求摘要"),
        Column("corp_id", identifier(190), nullable=False, comment="冻结企微企业身份"),
        Column("chat_id", identifier(190), nullable=False, comment="冻结目标群"),
        Column("sender_userid", identifier(190), nullable=False, comment="冻结实际群主"),
        Column(
            "group_binding_id",
            ID,
            ForeignKey("task_supplier_groups.id", name="fk_task_delivery_binding"),
            nullable=False,
            comment="供应商绑定",
        ),
        Column("group_binding_version", ID, nullable=False, comment="冻结绑定版本"),
        Column("snapshot_json", JSON, nullable=False, comment="正文、依据与合同清单快照，不含文件字节"),
        Column("snapshot_sha256", String(64), nullable=False, comment="冻结快照摘要"),
        Column(
            "status",
            String(32),
            nullable=False,
            comment="发送状态：preparing/submitting/pending_confirmation/sent/failed/unknown",
        ),
        Column("created_by", String(190), nullable=False, comment="认证提交身份"),
        Column("submitted_at", TIMESTAMP, comment="进入创建阶段时间 UTC"),
        Column("channel_message_id", identifier(190), comment="渠道 msgid"),
        Column("channel_status", String(32), comment="目标群渠道状态"),
        Column("sent_at", TIMESTAMP, comment="目标群实际发送时间 UTC"),
        Column("last_checked_at", TIMESTAMP, comment="最近查询时间 UTC"),
        Column("next_check_at", TIMESTAMP, comment="允许下次查询时间 UTC"),
        Column("error_code", String(64), comment="脱敏错误码"),
        Column("error_message", String(500), comment="脱敏说明"),
        Column("evidence_json", JSON, nullable=False, comment="素材编号与核实证据"),
        Column("lease_token", identifier(64), nullable=False, comment="执行领取令牌"),
        Column("lease_expires_at", TIMESTAMP, nullable=False, comment="领取有效期，不代表可以重发"),
        Column("resolved_by", String(190), comment="核实操作者"),
        Column("resolved_at", TIMESTAMP, comment="核实时间 UTC"),
        Column("resolution_reason", String(500), comment="核实原因"),
        *timestamps(),
        UniqueConstraint("notification_id", name="uq_task_delivery_notification"),
        UniqueConstraint("request_id", name="uq_task_delivery_request"),
        UniqueConstraint("corp_id", "channel_message_id", name="uq_task_delivery_message"),
        CheckConstraint(
            "status IN ('preparing','submitting','pending_confirmation','sent','failed','unknown')",
            name="ck_task_delivery_status",
        ),
        comment="企微通知执行及恢复证据",
        **table_options,
    )
    op.create_table(
        "task_notification_group_guards",
        Column("corp_id", identifier(190), primary_key=True, comment="企微企业身份"),
        Column("chat_id", identifier(190), primary_key=True, comment="客户群身份"),
        Column(
            "active_delivery_id",
            ID,
            ForeignKey("task_notification_deliveries.id", name="fk_task_group_guard_delivery"),
            comment="未决发送执行",
        ),
        *timestamps(),
        comment="同群跨任务发送互斥守卫",
        **table_options,
    )
    op.create_index(
        "ix_task_delivery_group", "task_notification_deliveries", ["corp_id", "chat_id", "created_at"]
    )
    op.create_index("ix_task_delivery_task", "task_notification_deliveries", ["task_id", "id"])
    if op.get_bind().dialect.name == "mysql":
        op.alter_column(
            "task_notifications",
            "channel",
            existing_type=String(24),
            existing_nullable=False,
            existing_server_default="manual",
            comment="通知渠道：manual 人工登记；wecom 企业微信渠道确认",
        )
        op.alter_column(
            "task_notifications",
            "channel_message_id",
            existing_type=String(190),
            existing_nullable=True,
            comment="企微目标群发送成功后保存的渠道消息 ID",
        )


def downgrade():
    raise RuntimeError("企微发送可能存在未决结果及渠道证据，不能降级删除，请关闭发送开关")
