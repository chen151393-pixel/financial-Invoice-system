"""settlement：保存银行交易时间及流水导入去重摘要。"""

import sqlalchemy as sa
from alembic import op

revision = "0048_settlement_receipt_import"
down_revision = "0047_settlement_bank_receipts"
branch_labels = None
depends_on = None

TABLE = "settlement_bank_receipts"
INDEX = "uq_settlement_bank_receipt_import_key"


def upgrade():
    if op.get_context().dialect.name == "mysql":
        op.execute(
            f"ALTER TABLE {TABLE} "
            "ADD COLUMN receipt_time TIME NULL COMMENT '银行交易时间，取导入表交易时间', "
            "ADD COLUMN import_key CHAR(64) NULL COMMENT '银行流水导入去重摘要，历史记录可为空', "
            f"ADD UNIQUE INDEX {INDEX} (import_key)"
        )
        return
    op.add_column(TABLE, sa.Column("receipt_time", sa.Time(), comment="银行交易时间，取导入表交易时间"))
    op.add_column(TABLE, sa.Column("import_key", sa.CHAR(64), comment="银行流水导入去重摘要，历史记录可为空"))
    op.create_index(INDEX, TABLE, ["import_key"], unique=True)


def downgrade():
    if not op.get_context().as_sql:
        if (
            op.get_bind()
            .execute(
                sa.text(
                    "SELECT 1 FROM settlement_bank_receipts WHERE import_key IS NOT NULL OR receipt_time IS NOT NULL LIMIT 1"
                )
            )
            .first()
        ):
            raise RuntimeError("银行收汇明细已有导入记录，拒绝丢弃去重依据及交易时间")
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_column(TABLE, "import_key")
    op.drop_column(TABLE, "receipt_time")
