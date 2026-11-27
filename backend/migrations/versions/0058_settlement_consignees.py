"""结汇客户唯一名称；存量名称由应用在启动工作线程前幂等补齐。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import identifier, table_options, timestamps

revision = "0058_settlement_consignees"
down_revision = "0057_review_customs_import_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "settlement_consignees",
        sa.Column(
            "name_key", identifier(500), primary_key=True, comment="去符号、空白并统一大写后的客户匹配键"
        ),
        sa.Column(
            "display_name", sa.String(500), nullable=False, comment="首次登记的客户原名；后续格式变体不覆盖"
        ),
        *timestamps(),
        comment="结汇客户名称归并；香港客户展示由环境配置覆盖",
        **table_options,
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM settlement_consignees")).scalar():
        raise RuntimeError("客户名称已有数据，不能自动删除名称归并记录")
    op.drop_table("settlement_consignees")
