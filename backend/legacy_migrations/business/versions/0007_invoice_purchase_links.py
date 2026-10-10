"""整票关联一张或多张子采购单，不写入数量金额分配台账。"""

import sqlalchemy as sa
from alembic import op

revision = "0007_invoice_purchase_links"
down_revision = "0006_approved_invoice_matching"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "invoice_purchase_link_batches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("invoice_id", sa.String(20), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "request_id", name="uq_invoice_link_request"),
        sa.UniqueConstraint("tenant_id", "invoice_id", name="uq_invoice_link_invoice"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "invoice_purchase_link_pairs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "batch_id", sa.Integer(), sa.ForeignKey("invoice_purchase_link_batches.id"), nullable=False
        ),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("invoice_line_id", sa.String(20), nullable=False),
        sa.Column("purchase_line_id", sa.String(20), nullable=False),
        sa.Column("purchase_order_id", sa.String(20), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("purchase_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("tenant_id", "purchase_line_id", name="uq_invoice_link_purchase_line"),
        sa.UniqueConstraint("batch_id", "invoice_line_id", "purchase_line_id", name="uq_invoice_link_pair"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade():
    raise RuntimeError("整票关联含人工确认记录，不自动删除")
