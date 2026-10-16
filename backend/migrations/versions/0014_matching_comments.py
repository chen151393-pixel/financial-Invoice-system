"""matching：补齐中文表与字段备注；降级仅恢复原备注，不删除业务数据。"""

from alembic import op
from backend.migrations.comment_ddl import apply_comments

revision = "0014_matching_comments"
down_revision = "0013_invoice_comments"
branch_labels = None
depends_on = None


def upgrade():
    apply_comments(op, "matching", "upgrade")


def downgrade():
    apply_comments(op, "matching", "downgrade")
