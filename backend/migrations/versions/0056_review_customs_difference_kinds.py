"""review：海关回执按差异类型计数与筛选（2026-11-25）。

在回执头上保存四类差异标记（数量、单位、总价、品名缺行），由比对结果派生，供概况卡计数和列表筛选。
已有回执先为 false，部署后由财务后台计算（算法版本 review-v18）自动重新比对并补齐，无需手工执行。
标记均可由比对结果重算，回退时直接删除这四列，不丢失业务数据。
"""

import sqlalchemy as sa
from alembic import op

revision = "0056_review_customs_difference_kinds"
down_revision = "0055_settlement_group_basis"
branch_labels = None
depends_on = None

COLUMNS = (
    ("quantity_mismatch", "比对含数量不一致的分组（含 NS 报关数量缺失）"),
    ("unit_mismatch", "比对含同品名单位不一致的分组"),
    ("total_mismatch", "比对含一对一行数量一致但总价不同的分组"),
    ("line_missing", "比对含单边缺行的分组（NS 无对应行或海关无对应项）"),
)


def upgrade():
    with op.batch_alter_table("review_customs_receipts") as batch:
        for name, comment in COLUMNS:
            batch.add_column(
                sa.Column(name, sa.Boolean, nullable=False, server_default=sa.text("0"), comment=comment)
            )


def downgrade():
    with op.batch_alter_table("review_customs_receipts") as batch:
        for name, _ in reversed(COLUMNS):
            batch.drop_column(name)
