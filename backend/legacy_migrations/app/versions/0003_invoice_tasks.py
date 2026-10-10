"""审核后持久化开票任务；不修改来源业务库或历史审核记录。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT, VARCHAR

revision = "0003_invoice_tasks"
down_revision = "0002_finance_review"
branch_labels = None
depends_on = None


def upgrade():
    def key(length):
        return sa.String(length).with_variant(VARCHAR(length, collation="utf8mb4_bin"), "mysql")

    op.create_table(
        "finance_invoice_tasks",
        sa.Column("id", key(36), primary_key=True),
        sa.Column("owner", key(200), nullable=False),
        sa.Column("account", key(100), nullable=False),
        sa.Column("declaration_id", key(190), nullable=False),
        sa.Column("snapshot_id", key(36), sa.ForeignKey("finance_review_snapshots.id"), nullable=False),
        sa.Column("review_revision", sa.Integer(), nullable=False),
        sa.Column("group_key", key(64), nullable=False),
        sa.Column("supplier_key", key(64), nullable=False),
        sa.Column("declaration_key", key(64), nullable=False),
        sa.Column("supplier", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(20), nullable=False),
        sa.Column("record_number", sa.String(190), nullable=False),
        sa.Column("status", key(30), nullable=False),
        sa.Column("payload", sa.Text().with_variant(LONGTEXT(), "mysql"), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("snapshot_id", "group_key", name="uq_finance_task_snapshot_group"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
    )
    op.create_index("ix_finance_task_owner_status", "finance_invoice_tasks", ["owner", "status"])
    op.create_index("ix_finance_task_review", "finance_invoice_tasks", ["owner", "account", "declaration_id"])


def downgrade():
    raise RuntimeError("开票任务关联历史审核，不允许直接删除；请使用后续增量迁移")
