"""source：子采购单币种取自母采购单，记录币种来源与待核实原因。

2026-10-15 只读核对正式 NS 账户：子采购单（customrecord_swc_subpo）没有独立币种、汇率或独立结算字段，
通过 custrecord_swc_subpo_mainpo 关联的母采购单（purchaseOrder）取得币种与汇率。

- source_parent_orders.exchange_rate：母采购汇率（SuiteQL exchangerate），作为换算依据保存。
- source_purchase_orders.currency_source：parent_order（取自母采购单）/ unresolved（待核实）。
- source_purchase_orders.currency_issue：待核实原因（没有母采购单、母采购单未返回币种等）。
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_source_purchase_currency"
down_revision = "0003_task_review_revision_and_notification_fields"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("source_parent_orders") as batch:
        batch.add_column(
            sa.Column("exchange_rate", sa.Numeric(28, 12), comment="母采购汇率（NS exchangerate）")
        )
    with op.batch_alter_table("source_purchase_orders") as batch:
        batch.add_column(
            sa.Column(
                "currency_source",
                sa.String(24),
                nullable=False,
                server_default="unresolved",
                comment="币种来源：parent_order / unresolved",
            )
        )
        batch.add_column(sa.Column("currency_issue", sa.String(300), comment="币种待核实原因"))
        batch.create_check_constraint(
            "ck_source_purchase_currency_source", "currency_source IN ('parent_order','unresolved')"
        )


def downgrade():
    with op.batch_alter_table("source_purchase_orders") as batch:
        batch.drop_constraint("ck_source_purchase_currency_source", type_="check")
        batch.drop_column("currency_issue")
        batch.drop_column("currency_source")
    with op.batch_alter_table("source_parent_orders") as batch:
        batch.drop_column("exchange_rate")
