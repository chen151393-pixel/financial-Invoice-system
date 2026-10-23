"""source：销售单单头（币种、汇率）与子采购单的销售单关联，供申报幅度与发票价格校验（2026-10-23）。

汇率不参与报关单内容摘要，新增后不会使已审核的报关单变为需重审。
"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP, table_options, timestamps

revision = "0029_source_sales_orders"
down_revision = "0028_task_document_completion"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_sales_orders",
        sa.Column(
            "id",
            ID,
            primary_key=True,
            autoincrement=True,
            comment="本地自增主键；与 NS 内部 ID、单号分开保存",
        ),
        sa.Column(
            "ns_account", sa.String(100), nullable=False, comment="NS 账套标识，用于隔离正式、沙箱等来源"
        ),
        sa.Column("ns_internal_id", sa.String(190), nullable=False, comment="NS 销售单内部 ID"),
        sa.Column("order_no", sa.String(150), comment="销售单号（NS tranid），与报关行销售订单号对照"),
        sa.Column("currency", sa.String(20), comment="币种代码，例如 USD；无法识别时为空"),
        sa.Column("currency_name", sa.String(100), comment="NS 返回的币种名称原文，供追溯"),
        sa.Column(
            "exchange_rate",
            sa.Numeric(28, 12),
            comment="NS exchangerate：1 单位本币种折合人民币；缺失为空，不以 1 代替",
        ),
        sa.Column("synced_at", TIMESTAMP, nullable=False, comment="本次成功保存来源数据的时间，UTC"),
        *timestamps(),
        sa.UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_sales_ns"),
        comment="销售单单头（币种、汇率），用于申报幅度与发票价格校验；不参与报关单内容摘要",
        **table_options,
    )
    with op.batch_alter_table("source_purchase_orders") as batch:
        batch.add_column(
            sa.Column(
                "sales_order_id",
                ID,
                sa.ForeignKey("source_sales_orders.id", name="fk_source_purchase_sales"),
                comment="子采购单对应的销售单本地主键（NS custrecord_swc_subpo_so）",
            )
        )


def downgrade():
    raise RuntimeError("销售单汇率可能已被申报幅度与价格校验使用，不能降级删除；请保留数据")
