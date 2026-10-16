"""invoice 版本化补强；不删除旧表或 v2 数据。上线后不可回退删除版本证据。"""

from alembic import op
from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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


revision = "0008_invoice_ledger_versions"
down_revision = "0007_task_ledger_versions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "invoice_versions",
        Column("id", ID, primary_key=True, autoincrement=True),
        Column(
            "invoice_id",
            ID,
            ForeignKey("invoice_headers.id", name="fk_invoice_version_header"),
            nullable=False,
        ),
        Column("revision", Integer, nullable=False),
        Column("content_sha256", CHAR(64), nullable=False),
        Column("raw_record_id", ID),
        Column("source", String(40), nullable=False),
        Column("external_id", String(255)),
        Column("currency_source", String(24), nullable=False),
        Column("source_rule_version", String(40)),
        Column("header_snapshot", JSON, nullable=False),
        Column("items_snapshot", JSON, nullable=False),
        *timestamps(),
        UniqueConstraint("invoice_id", "revision", name="uq_invoice_version_revision"),
        Index("ix_invoice_version_content", "invoice_id", "content_sha256"),
        **table_options,
    )
    with op.batch_alter_table("invoice_headers") as batch:
        batch.add_column(Column("current_version_id", ID))
        batch.add_column(Column("detail_status", String(24), nullable=False, server_default="complete"))
    with op.batch_alter_table("invoice_items") as batch:
        batch.add_column(Column("is_active", Boolean, nullable=False, server_default="1"))
    from backend.migrations.backfill_invoice import backfill

    if not op.get_context().as_sql:
        backfill(op.get_bind())


def downgrade():
    raise RuntimeError("版本证据不可丢弃，请通过后续修复迁移处理；不得降级清空台账")
