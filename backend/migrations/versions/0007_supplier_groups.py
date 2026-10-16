"""供应商默认企微群、配置历史及导入群目录。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT, VARCHAR

revision = "0007_supplier_groups"
down_revision = "0006_task_notifications"
branch_labels = None
depends_on = None


def upgrade():
    def key(length):
        return sa.String(length).with_variant(VARCHAR(length, collation="utf8mb4_bin"), "mysql")

    options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}
    op.create_table(
        "finance_supplier_groups",
        sa.Column("owner", key(200), primary_key=True),
        sa.Column("account", key(100), primary_key=True),
        sa.Column("supplier_id", key(190), primary_key=True),
        sa.Column("supplier_key", key(64), nullable=False),
        sa.Column("supplier_name", sa.String(255), nullable=False),
        sa.Column("group_name", sa.String(200), nullable=False),
        sa.Column("chat_id", key(190), nullable=False),
        sa.Column("employee", sa.String(100), nullable=False),
        sa.Column("userid", key(190), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("owner", "account", "supplier_key", name="uq_supplier_group_key"),
        **options,
    )
    op.create_table(
        "finance_supplier_group_history",
        sa.Column("owner", key(200), primary_key=True),
        sa.Column("account", key(100), primary_key=True),
        sa.Column("supplier_id", key(190), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("at", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.Text().with_variant(LONGTEXT(), "mysql"), nullable=False),
        **options,
    )
    op.create_table(
        "finance_wecom_group_directory",
        sa.Column("owner", key(200), primary_key=True),
        sa.Column("chat_id", key(190), primary_key=True),
        sa.Column("group_name", sa.String(200), nullable=False),
        sa.Column("employee", sa.String(100), nullable=False),
        sa.Column("userid", key(190), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        **options,
    )


def downgrade():
    raise RuntimeError("群配置历史用于追溯，不允许直接删除；请使用增量迁移")
