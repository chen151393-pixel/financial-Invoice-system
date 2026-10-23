"""source：报关单保存 NS 创建时间，用于归档文件夹的月份（2026-10-23 业务确认按报关单创建日期）。

已入库的报关单在下次同步时补齐；NS 未返回时保持为空，不用其他日期代替。
"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import TIMESTAMP

revision = "0027_source_customs_created_at"
down_revision = "0026_task_supplier_settings"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("source_customs_declarations") as batch:
        batch.add_column(
            sa.Column(
                "ns_created_at",
                TIMESTAMP,
                comment="NS 报关单创建时间（created），UTC；归档月份按中国时间取",
            )
        )


def downgrade():
    with op.batch_alter_table("source_customs_declarations") as batch:
        batch.drop_column("ns_created_at")
