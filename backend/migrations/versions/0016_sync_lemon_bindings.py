"""sync：持久化柠檬云绑定结果；降级拒绝丢弃绑定证据。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP, identifier, table_options, timestamps

revision = "0016_sync_lemon_bindings"
down_revision = "0015_sync_comments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sync_lemon_bindings",
        sa.Column("id", ID, primary_key=True, autoincrement=True, comment="绑定记录主键"),
        sa.Column("scope_key", identifier(64), nullable=False, comment="环境、应用与操作身份的摘要"),
        sa.Column("owner", identifier(190), nullable=False, comment="发起绑定的认证身份"),
        sa.Column("mobile", identifier(32), nullable=False, comment="绑定的已有账号手机号"),
        sa.Column("status", identifier(20), nullable=False, comment="未绑定、绑定中、结果未知或已绑定"),
        sa.Column("verified_at", TIMESTAMP, nullable=True, comment="最近确认绑定成功时间，UTC"),
        *timestamps(),
        sa.UniqueConstraint("scope_key", name="uq_sync_lemon_binding_scope"),
        sa.CheckConstraint(
            "status IN ('unbound','binding','unknown','bound')", name="ck_sync_lemon_binding_status"
        ),
        comment="柠檬云已有账号绑定状态，不保存凭据",
        **table_options,
    )


def downgrade():
    raise RuntimeError("绑定版本证据不可丢弃，请保留 sync_lemon_bindings")
