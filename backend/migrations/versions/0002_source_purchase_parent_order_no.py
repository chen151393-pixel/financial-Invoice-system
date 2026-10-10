"""source：子采购单保存母采购单号。

同步读取的母采购单号（NS custrecord_swc_subpo_mainpo）是展示与追溯字段；
母采购单表只由内部快照导入填充，同步时可能尚无对应行，因此单独保存单号文本。
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_source_purchase_parent_order_no"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("source_purchase_orders") as batch:
        batch.add_column(sa.Column("parent_order_no", sa.String(150), comment="母采购单号（来源文本）"))


def downgrade():
    with op.batch_alter_table("source_purchase_orders") as batch:
        batch.drop_column("parent_order_no")
