"""matching 版本化补强；不删除旧表或 v2 数据。上线后不可回退删除版本证据。"""

from alembic import op
from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, Numeric, String, text
from sqlalchemy.dialects.mysql import BIGINT, DATETIME

ID = BigInteger().with_variant(BIGINT(unsigned=True), "mysql").with_variant(Integer(), "sqlite")
TIMESTAMP = DateTime().with_variant(DATETIME(fsp=6), "mysql")
table_options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}


def timestamps():
    return [
        Column(
            "created_at",
            TIMESTAMP,
            nullable=False,
            server_default=text(
                "CURRENT_TIMESTAMP(6)" if op.get_context().dialect.name == "mysql" else "CURRENT_TIMESTAMP"
            ),
        ),
        Column(
            "updated_at",
            TIMESTAMP,
            nullable=False,
            server_default=text(
                "CURRENT_TIMESTAMP(6)" if op.get_context().dialect.name == "mysql" else "CURRENT_TIMESTAMP"
            ),
        ),
    ]


revision = "0009_matching_ledger_versions"
down_revision = "0008_invoice_ledger_versions"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("matching_allocations") as batch:
        batch.add_column(Column("invoice_version_id", ID))
        batch.add_column(Column("purchase_basis_id", ID))
        batch.add_column(Column("purchase_quantity", Numeric(26, 8)))
        batch.add_column(Column("invoice_unit", String(50)))
        batch.add_column(Column("purchase_unit", String(50)))
        batch.add_column(Column("conversion_numerator", Numeric(28, 12)))
        batch.add_column(Column("conversion_denominator", Numeric(28, 12)))
        batch.add_column(Column("conversion_evidence", JSON))
        batch.add_column(
            Column("verification_status", String(24), nullable=False, server_default="needs_review")
        )
        batch.add_column(Column("verification_issues", JSON))
        batch.add_column(Column("verification_history", JSON))
        batch.add_column(Column("rule_version", String(40), nullable=False, server_default="ledger_v2"))
    from backend.migrations.backfill_matching import backfill

    if not op.get_context().as_sql:
        backfill(op.get_bind())


def downgrade():
    raise RuntimeError("版本证据不可丢弃，请通过后续修复迁移处理；不得降级清空台账")
