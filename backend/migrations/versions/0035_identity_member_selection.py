"""人员选择预览与独立启用开关；保留已有账号，不允许降级丢失权限状态。"""

from alembic import op
from backend.core.schema import TIMESTAMP, table_options, timestamps
from sqlalchemy import JSON, Boolean, Column, String, text

revision = "0035_identity_member_selection"
down_revision = "0034_source_customs_declared_unit_price"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "identity_users",
        Column(
            "enabled",
            Boolean,
            nullable=False,
            server_default=text("1"),
            comment="管理员是否启用；新导入默认待授权，同步不覆盖",
        ),
    )
    # 只为迁移前的人员保留现有登录行为；以后新导入必须明确授权。
    with op.batch_alter_table("identity_users") as batch:
        batch.alter_column("enabled", existing_type=Boolean(), server_default=text("0"))
    op.create_table(
        "identity_directory_previews",
        Column("id", String(64), primary_key=True, comment="随机预览标识"),
        Column("actor", String(200), nullable=False, comment="创建预览的管理员"),
        Column("version", String(64), nullable=False, comment="读取前权限数据摘要，确认时复核"),
        Column("payload", JSON, nullable=False, comment="飞书部门与成员快照，过期清除"),
        Column("expires_at", TIMESTAMP, nullable=False, comment="预览过期时间，UTC"),
        Column("result", JSON, comment="已确认的范围与结果，用于幂等重试"),
        *timestamps(),
        comment="短期飞书组织预览；有效期十分钟",
        **table_options,
    )
    op.create_table(
        "identity_user_sync_scopes",
        Column("user_id", String(64), primary_key=True, comment="单独选择的飞书 user_id"),
        Column("created_by", String(200), nullable=False, comment="设置范围的认证操作者"),
        *timestamps(),
        comment="个人同步范围，与部门范围取并集",
        **table_options,
    )


def downgrade():
    raise RuntimeError("人员范围和授权状态可能已被使用，不能降级删除；请保留数据")
