"""区分待核实、确认无母单及已关联，并预留 NS 母行原始标识。"""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

revision = "0002_parent_relation_status"
down_revision = "0001_business_parents"
branch_labels = None
depends_on = None


def upgrade():
    if not context.is_offline_mode():
        inspector = sa.inspect(op.get_bind())
        for table, field in (
            ("purchase_orders", "parent_relation_status"),
            ("purchase_order_lines", "ns_parent_line_ref"),
        ):
            if field in {column["name"] for column in inspector.get_columns(table)}:
                raise RuntimeError("母采购状态或原始行标识字段已存在，请先核实是否有中断迁移")

    op.add_column(
        "purchase_orders",
        sa.Column(
            "parent_relation_status",
            sa.String(16, collation="utf8mb4_bin"),
            nullable=False,
            server_default="unknown",
            comment="母单关系：unknown待核实，no_parent已核实无母单，linked已关联",
        ),
    )
    # 只承认已有外键，不根据显示单号猜关联；历史空引用不能推断为无母单。
    op.execute(
        "UPDATE purchase_orders SET parent_relation_status = 'linked' "
        "WHERE parent_purchase_order_id IS NOT NULL"
    )
    op.create_check_constraint(
        "ck_purchase_parent_relation",
        "purchase_orders",
        "(parent_relation_status IN ('unknown', 'no_parent') AND parent_purchase_order_id IS NULL) "
        "OR (parent_relation_status = 'linked' AND parent_purchase_order_id IS NOT NULL)",
    )
    op.alter_column(
        "purchase_orders",
        "parent_purchase_order_id",
        existing_type=mysql.BIGINT(unsigned=True),
        existing_nullable=True,
        existing_server_default=None,
        comment="关联母采购本地主键；空值含义由parent_relation_status区分",
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column(
            "ns_parent_line_ref",
            sa.String(190, collation="utf8mb4_bin"),
            nullable=True,
            comment="NS母行原始标识custrecord_swc_subpo_item_mainpo_lineid，非本地主键",
        ),
    )


def downgrade():
    raise RuntimeError("母采购关系状态及原始行标识可能已有数据，不提供自动删字段降级")
