"""保留 NS 报关单价来源精度，不对导入值静默舍入。"""

import sqlalchemy as sa
from alembic import context, op

revision = "0003_customs_price_precision"
down_revision = "0002_parent_relation_status"
branch_labels = None
depends_on = None


def upgrade():
    if not context.is_offline_mode():
        columns = sa.inspect(op.get_bind()).get_columns("customs_declaration_lines")
        column = next(row for row in columns if row["name"] == "unit_price")
        kind = column["type"]
        if not isinstance(kind, sa.Numeric) or (kind.precision, kind.scale) != (24, 8):
            raise RuntimeError("报关单价列不是预期的 DECIMAL(24,8)，请核实实际结构及迁移状态")
    op.alter_column(
        "customs_declaration_lines",
        "unit_price",
        type_=sa.Numeric(38, 18),
        existing_type=sa.Numeric(24, 8),
        existing_nullable=True,
        existing_server_default=None,
        comment="来源明细单价，保留NS原始小数精度；含税口径按来源字段确认",
    )


def downgrade():
    raise RuntimeError("缩小单价精度可能损失来源值，不提供自动降级")
