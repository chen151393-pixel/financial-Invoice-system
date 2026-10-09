"""新合同仅保存共享盘路径与元数据，不删除旧版原件。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGBLOB

revision = "0008_contract_metadata"
down_revision = "0007_supplier_groups"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite 需重建表以修改可空性；Alembic 保留数据与约束，MySQL 使用 ALTER。
    with op.batch_alter_table("finance_task_documents") as batch:
        batch.alter_column(
            "content",
            existing_type=sa.LargeBinary().with_variant(LONGBLOB(), "mysql"),
            existing_nullable=False,
            nullable=True,
        )


def downgrade():
    raise RuntimeError("仅保存路径的合同不能恢复数据库原件，请使用增量迁移")
