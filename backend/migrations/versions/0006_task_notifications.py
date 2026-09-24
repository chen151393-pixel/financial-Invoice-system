"""开票通知草稿和人工发送登记保留不可变版本。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT, VARCHAR

revision = "0006_task_notifications"
down_revision = "0005_contract_archive"
branch_labels = None
depends_on = None


def upgrade():
    def key(length):
        return sa.String(length).with_variant(VARCHAR(length, collation="utf8mb4_bin"), "mysql")

    op.create_table(
        "finance_task_notifications",
        sa.Column("task_id", key(36), sa.ForeignKey("finance_invoice_tasks.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("actor", key(200), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.Text().with_variant(LONGTEXT(), "mysql"), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
    )


def downgrade():
    raise RuntimeError("通知历史用于追溯，不允许直接删除；请使用增量迁移")
