"""source：报关明细保存申报单价（2026-10-28）。

申报幅度与发票单价校验按报关数量、报关单位和申报单价（NS custrecord_swc_grossamountzj）计算，
与 NS 报关单打印口径一致；原 unit_price（custrecord_swc_unitprice）与 quantity / unit 配套，继续保留。
已有数据为 NULL，重新同步后补齐；NULL 表示未知，不按 0 处理。
"""

import sqlalchemy as sa
from alembic import op

revision = "0034_source_customs_declared_unit_price"
down_revision = "0033_identity_directory"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("source_customs_lines") as batch:
        batch.add_column(
            sa.Column(
                "declared_unit_price",
                sa.Numeric(24, 8),
                comment="申报单价（NS custrecord_swc_grossamountzj），与 declared_quantity / declared_unit 配套；"
                "申报幅度与发票单价校验使用它",
            )
        )


def downgrade():
    with op.batch_alter_table("source_customs_lines") as batch:
        batch.drop_column("declared_unit_price")
