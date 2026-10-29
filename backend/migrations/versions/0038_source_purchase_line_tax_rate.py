"""source：子采购明细保存税率（2026-10-29）。

NS 子采购明细的税字段 custrecord_swc_subpo_item_tax 是税码引用（显示名如“13%”），没有税额。
发票整单比对按“含税合计 × 税率 ÷（1 + 税率）”核对票面税额，需要该税率。
已有数据为 NULL，重新同步后补齐；NULL 表示未知，比对显示“未校验”，不按 0 处理。
"""

import sqlalchemy as sa
from alembic import op

revision = "0038_source_purchase_line_tax_rate"
down_revision = "0037_writeback_execution"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("source_purchase_order_lines") as batch:
        batch.add_column(
            sa.Column(
                "tax_rate",
                sa.Numeric(8, 6),
                comment="税率小数（0.13 表示 13%），由 NS 税码显示名解析；无法解析或未返回时为 NULL",
            )
        )


def downgrade():
    with op.batch_alter_table("source_purchase_order_lines") as batch:
        batch.drop_column("tax_rate")
