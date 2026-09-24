"""共享盘成功保存后才完成资料节点；保留已下载 PDF 供补存。"""

import sqlalchemy as sa
from alembic import op

revision = "0005_contract_archive"
down_revision = "0004_task_documents"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("finance_task_documents", sa.Column("archive_path", sa.String(2048)))
    op.add_column("finance_task_documents", sa.Column("archived_at", sa.BigInteger()))
    op.execute("UPDATE finance_invoice_tasks SET status='documents_pending' WHERE status='notify_pending'")


def downgrade():
    raise RuntimeError("共享盘记录用于追溯，不允许直接删除；请使用增量迁移")
