"""审核通过即待下载采购原件，保存已校验的合同 PDF。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGBLOB, VARCHAR

revision = "0004_task_documents"
down_revision = "0003_invoice_tasks"
branch_labels = None
depends_on = None


def upgrade():
    def key(length):
        return sa.String(length).with_variant(VARCHAR(length, collation="utf8mb4_bin"), "mysql")

    op.create_table(
        "finance_task_documents",
        sa.Column("task_id", key(36), sa.ForeignKey("finance_invoice_tasks.id"), primary_key=True),
        sa.Column("order_id", key(190), primary_key=True),
        sa.Column("environment", key(100), nullable=False),
        sa.Column("ns_id", key(40), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sha256", key(64), nullable=False),
        sa.Column("content", sa.LargeBinary().with_variant(LONGBLOB(), "mysql"), nullable=False),
        sa.Column("downloaded_at", sa.BigInteger(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
    )
    op.execute("UPDATE finance_invoice_tasks SET status='documents_pending' WHERE status='scope_pending'")


def downgrade():
    raise RuntimeError("采购原件用于审核追溯，不允许直接删除；请使用增量迁移")
