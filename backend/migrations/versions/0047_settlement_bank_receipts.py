"""settlement：银行收汇明细（直接收汇明细总账的收汇来源）。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP, identifier, table_options, timestamps
from sqlalchemy import Column, Date, Index, Integer, MetaData, Numeric, String, Table

revision = "0047_settlement_bank_receipts"
down_revision = "0046_settlement_documents"
branch_labels = None
depends_on = None
metadata = MetaData()

bank_receipts = Table(
    "settlement_bank_receipts",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="银行收汇记录本地主键"),
    Column("receipt_date", Date, nullable=False, comment="收汇日期（银行入账日期）"),
    Column("receiving_company", String(200), nullable=False, comment="收汇抬头：我方收款主体，如上海毅鑫"),
    Column("receiving_account", String(200), comment="收款账户（境内美金账户）"),
    Column("payer_name", String(500), nullable=False, comment="付款人户名（银行流水原文）"),
    Column(
        "payer_key",
        identifier(500),
        nullable=False,
        comment="付款人户名规范化名称；与 customer_key 不同即三方代付",
    ),
    Column(
        "customer_name",
        String(500),
        nullable=False,
        comment="实际客户，即境外收货人；取导入表格填写的值，与付款人户名不同时为三方代付",
    ),
    Column(
        "customer_key",
        identifier(500),
        nullable=False,
        comment="实际客户规范化名称，与海关回执境外收货人的规范化名称相等时归到同一收货人",
    ),
    Column("currency", String(20), nullable=False, comment="币种代码，如 USD"),
    Column("amount", Numeric(24, 6), nullable=False, comment="收汇金额，与 currency 配套"),
    Column("reference", String(200), comment="银行流水号"),
    Column("source_file", String(255), comment="导入来源文件名"),
    Column("source_row", Integer, comment="来源文件中的行号，便于核对"),
    Column("imported_by", String(190), nullable=False, comment="导入人（认证身份）"),
    Column("imported_at", TIMESTAMP, nullable=False, comment="导入时间，UTC"),
    *timestamps(),
    Index("ix_settlement_bank_receipt_date", "receipt_date"),
    Index("ix_settlement_bank_receipt_customer", "customer_key", "currency"),
    comment="银行收汇明细：境内美金账户收汇记录及其对应的实际客户（境外收货人）",
    **table_options,
)


def upgrade():
    bank_receipts.create(op.get_bind())


def downgrade():
    # 银行收汇记录是收汇凭证，有数据时不允许降级删除。
    if not op.get_context().as_sql:
        if op.get_bind().execute(sa.text("SELECT 1 FROM settlement_bank_receipts")).first():
            raise RuntimeError("银行收汇明细已有数据，不能降级删除；请保留数据")
    bank_receipts.drop(op.get_bind())
