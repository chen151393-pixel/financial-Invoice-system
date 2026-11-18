"""保存直接收汇的确认分配。"""

from alembic import op
from backend.core.schema import ID, TIMESTAMP, identifier, table_options
from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Numeric, String, UniqueConstraint, text

revision = "0049_settlement_direct_allocations"
down_revision = "0048_settlement_receipt_import"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "settlement_direct_allocations",
        Column("id", ID, primary_key=True, autoincrement=True),
        Column("receipt_id", ID, ForeignKey("settlement_bank_receipts.id"), nullable=False),
        Column("bank_reference", String(200), nullable=False),
        Column("declaration_no", identifier(150), nullable=False),
        Column("amount", Numeric(24, 6), nullable=False),
        Column("request_id", String(36), nullable=False),
        Column("confirmed_at", TIMESTAMP, nullable=False),
        Column("confirmed_by", String(190), nullable=False),
        CheckConstraint("amount > 0", name="ck_settlement_direct_amount"),
        UniqueConstraint("request_id", "declaration_no", name="uq_settlement_direct_request_decl"),
        **table_options,
    )
    for key in ("receipt", "declaration"):
        column = "receipt_id" if key == "receipt" else "declaration_no"
        Index(f"ix_settlement_direct_{key}", table.c[column]).create(op.get_bind())


def downgrade():
    if (
        not op.get_context().as_sql
        and op.get_bind().execute(text("SELECT 1 FROM settlement_direct_allocations LIMIT 1")).first()
    ):
        raise RuntimeError("已有直接收汇分配记录，不能降级删除")
    op.drop_table("settlement_direct_allocations")
