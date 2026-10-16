"""review 版本化补强；不删除旧表或 v2 数据。上线后不可回退删除版本证据。"""

from alembic import op
from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
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


revision = "0006_review_ledger_versions"
down_revision = "0005_source_ledger_versions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_purchase_bases",
        Column("id", ID, primary_key=True, autoincrement=True),
        Column("ns_account", String(100), nullable=False),
        Column("purchase_order_id", ID, nullable=False),
        Column("purchase_line_id", ID, nullable=False),
        Column("revision", Integer, nullable=False),
        Column("status", String(24), nullable=False),
        Column(
            "current_purchase_line_id",
            ID,
            Computed("CASE WHEN status <> 'superseded' THEN purchase_line_id END", persisted=True),
        ),
        Column("supplier_id", ID),
        Column("company_id", ID),
        Column("currency", String(20)),
        Column("quantity", Numeric(26, 8)),
        Column("unit", String(50)),
        Column("amount", Numeric(24, 6)),
        Column("currency_source", String(24), nullable=False),
        Column("source_sha256", CHAR(64), nullable=False),
        Column("basis_sha256", CHAR(64), nullable=False),
        Column("source_refs", JSON, nullable=False),
        Column("currency_evidence", JSON),
        Column("origin_review_id", ID, nullable=False),
        Column("approved_by", String(200), nullable=False),
        Column("approved_at", TIMESTAMP, nullable=False),
        *timestamps(),
        UniqueConstraint("purchase_line_id", "revision", name="uq_review_basis_revision"),
        UniqueConstraint("current_purchase_line_id", name="uq_review_basis_current"),
        Index("ix_review_basis_order", "purchase_order_id"),
        CheckConstraint("status IN ('active','review_required','superseded')", name="ck_review_basis_status"),
        **table_options,
    )
    with op.batch_alter_table("review_lines") as batch:
        batch.add_column(Column("purchase_basis_id", ID))
    from backend.migrations.backfill_review import backfill

    if not op.get_context().as_sql:
        backfill(op.get_bind())


def downgrade():
    raise RuntimeError("版本证据不可丢弃，请通过后续修复迁移处理；不得降级清空台账")
