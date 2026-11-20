"""直接收汇资料组：保留已有单票与香港资料，新增跨抬头共用提单范围。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP, identifier, table_options

revision = "0051_settlement_document_groups"
down_revision = "0050_settlement_direct_documents"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "settlement_document_groups",
        sa.Column("id", ID, primary_key=True, autoincrement=True),
        sa.Column("group_no", identifier(40), nullable=False, unique=True),
        sa.Column("request_id", identifier(36), nullable=False, unique=True),
        sa.Column("consignee", sa.String(200), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("created_by", sa.String(190), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        **table_options,
    )
    op.create_table(
        "settlement_document_group_items",
        sa.Column("id", ID, primary_key=True, autoincrement=True),
        sa.Column("group_id", ID, sa.ForeignKey("settlement_document_groups.id"), nullable=False),
        sa.Column("declaration_no", identifier(150), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.UniqueConstraint("declaration_no", name="uq_settlement_document_group_declaration"),
        **table_options,
    )
    for kind in ("bill", "contract"):
        with op.batch_alter_table(f"settlement_{kind}s") as batch:
            batch.drop_constraint(f"ck_settlement_{kind}_source", type_="check")
            batch.add_column(sa.Column("document_group_id", ID, comment="所属直接收汇资料组"))
            batch.create_foreign_key(
                f"fk_settlement_{kind}_group", "settlement_document_groups", ["document_group_id"], ["id"]
            )
            batch.create_check_constraint(
                f"ck_settlement_{kind}_source",
                "(CASE WHEN batch_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN direct_declaration_no IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN document_group_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            )
            if kind == "contract":
                batch.add_column(sa.Column("document_key", identifier(64)))
                batch.create_unique_constraint(
                    "uq_settlement_contract_group_key", ["document_group_id", "document_key"]
                )
            else:
                batch.create_index("ix_settlement_bill_group", ["document_group_id", "removed_at"])


def downgrade():
    if (
        not op.get_context().as_sql
        and op.get_bind().execute(sa.text("SELECT 1 FROM settlement_document_groups LIMIT 1")).first()
    ):
        raise RuntimeError("已有直接收汇资料组，拒绝回退并丢失资料归属")
    for kind in ("bill", "contract"):
        with op.batch_alter_table(f"settlement_{kind}s") as batch:
            batch.drop_constraint(f"ck_settlement_{kind}_source", type_="check")
            batch.drop_constraint(f"fk_settlement_{kind}_group", type_="foreignkey")
            if kind == "contract":
                batch.drop_constraint("uq_settlement_contract_group_key", type_="unique")
                batch.drop_column("document_key")
            else:
                batch.drop_index("ix_settlement_bill_group")
            batch.drop_column("document_group_id")
            batch.create_check_constraint(
                f"ck_settlement_{kind}_source",
                "(batch_id IS NOT NULL AND direct_declaration_no IS NULL) OR (batch_id IS NULL AND direct_declaration_no IS NOT NULL)",
            )
    op.drop_table("settlement_document_group_items")
    op.drop_table("settlement_document_groups")
