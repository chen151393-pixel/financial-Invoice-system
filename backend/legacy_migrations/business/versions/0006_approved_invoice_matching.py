"""在既有分配台账中保存已审核报关行和明确的子采购来源身份。"""

import sqlalchemy as sa
from alembic import op

revision = "0006_approved_invoice_matching"
down_revision = "0005_customs_relations"
branch_labels = None
depends_on = None


def upgrade():
    # 历史分配仍保留原采购行；新分配以NS明确的采购来源组为身份，可能包含多条子行。
    op.alter_column("invoice_purchase_allocations", "purchase_line_id", existing_type=sa.String(20), nullable=True)
    for name, column_type in (
        ("purchase_order_id", sa.String(20)),
        ("purchase_key", sa.String(64)),
        ("customs_line_id", sa.String(20)),
        ("review_account", sa.String(100)),
        ("review_declaration_id", sa.String(190)),
        ("review_snapshot_id", sa.String(36)),
        ("review_revision", sa.Integer()),
        ("review_digest", sa.String(64)),
    ):
        op.add_column("invoice_purchase_allocations", sa.Column(name, column_type, nullable=True))
    op.create_index(
        "ix_invoice_allocation_customs", "invoice_purchase_allocations", ["tenant_id", "customs_line_id"]
    )
    op.create_index(
        "ix_invoice_allocation_purchase", "invoice_purchase_allocations", ["tenant_id", "purchase_key"]
    )


def downgrade():
    raise RuntimeError("分配表含已确认的报关行及采购来源，不自动删除或降级")
