"""source 版本化补强；不删除旧表或 v2 数据。上线后不可回退删除版本证据。"""

from alembic import op
from sqlalchemy import BigInteger, Column, DateTime, Integer, String, text
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


revision = "0005_source_ledger_versions"
down_revision = "0004_source_purchase_currency"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("source_parent_orders") as batch:
        batch.add_column(Column("currency_internal_id", String(100)))
    with op.batch_alter_table("source_purchase_orders") as batch:
        batch.add_column(Column("currency_raw_record_id", ID))


def downgrade():
    raise RuntimeError("版本证据不可丢弃，请通过后续修复迁移处理；不得降级清空台账")
