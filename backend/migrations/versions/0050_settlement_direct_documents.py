"""直接收汇资料按报关单保存，与香港收款批次独立，保留已有资料。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, identifier

revision = "0050_settlement_direct_documents"
down_revision = "0049_settlement_direct_allocations"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("bill", "contract"):
        table = f"settlement_{name}s"
        with op.batch_alter_table(table) as batch:
            batch.alter_column("batch_id", existing_type=ID, nullable=True)
            batch.add_column(
                sa.Column(
                    "direct_declaration_no", identifier(150), comment="直接收汇资料所属报关单；与批次二选一"
                )
            )
            batch.create_check_constraint(
                f"ck_settlement_{name}_source",
                "(batch_id IS NOT NULL AND direct_declaration_no IS NULL) OR (batch_id IS NULL AND direct_declaration_no IS NOT NULL)",
            )
            if name == "bill":
                batch.create_index("ix_settlement_bill_direct", ["direct_declaration_no", "removed_at"])
            else:
                batch.create_unique_constraint(
                    "uq_settlement_contract_direct_no", ["direct_declaration_no", "contract_no"]
                )


def downgrade():
    if not op.get_context().as_sql:
        for name in ("bill", "contract"):
            if (
                op.get_bind()
                .execute(
                    sa.text(
                        f"SELECT 1 FROM settlement_{name}s WHERE direct_declaration_no IS NOT NULL LIMIT 1"
                    )
                )
                .first()
            ):
                raise RuntimeError("已有直接收汇资料，拒绝回退并丢弃资料关联")
    for name in ("bill", "contract"):
        with op.batch_alter_table(f"settlement_{name}s") as batch:
            if name == "bill":
                batch.drop_index("ix_settlement_bill_direct")
            else:
                batch.drop_constraint("uq_settlement_contract_direct_no", type_="unique")
            batch.drop_constraint(f"ck_settlement_{name}_source", type_="check")
            batch.drop_column("direct_declaration_no")
            batch.alter_column("batch_id", existing_type=ID, nullable=False)
