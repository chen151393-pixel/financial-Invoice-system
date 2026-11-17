"""settlement：结汇资料包——提单、按模板生成的销售合同、合同抬头与印章。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP, identifier, table_options, timestamps
from sqlalchemy import (
    CHAR,
    JSON,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)

revision = "0046_settlement_documents"
down_revision = "0045_settlement_batches"
branch_labels = None
depends_on = None
metadata = MetaData()

# 仅用于外键解析；该表由 0045 创建
Table("settlement_batches", metadata, Column("id", ID, primary_key=True))

bills = Table(
    "settlement_bills",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="提单本地主键"),
    Column(
        "batch_id",
        ID,
        ForeignKey("settlement_batches.id", name="fk_settlement_bill_batch"),
        nullable=False,
        comment="所属结汇批次，指向 settlement_batches.id",
    ),
    Column("file_id", identifier(36), nullable=False, comment="资料目录中的文件标识（服务端生成的 UUID）"),
    Column("file_name", String(255), nullable=False, comment="上传时的原文件名，仅展示"),
    Column("sha256", CHAR(64), nullable=False, comment="文件内容 SHA-256，用于识别同一批次内重复上传"),
    Column("size_bytes", Integer, nullable=False, comment="文件大小，字节"),
    Column("bl_no", String(100), comment="提单号；解析得到或人工填写"),
    Column("port_of_loading", String(200), comment="装运口岸（英文，取自提单）"),
    Column("port_of_discharge", String(200), comment="目的口岸（英文，取自提单）"),
    Column("on_board_date", Date, comment="装船日期"),
    Column("declaration_nos", JSON, nullable=False, comment="该提单对应的报关单号列表（须属于本批次）"),
    Column("parse_note", String(500), comment="自动解析说明，如未能读取文字需人工填写"),
    Column("uploaded_by", String(190), nullable=False, comment="上传人（认证身份）"),
    Column("uploaded_at", TIMESTAMP, nullable=False, comment="上传时间，UTC"),
    Column("confirmed_by", String(190), comment="最近一次人工修改字段的操作人"),
    Column("removed_by", String(190), comment="移除人；未移除为空"),
    Column("removed_at", TIMESTAMP, comment="移除时间，UTC；非空表示已移除"),
    *timestamps(),
    Index("ix_settlement_bill_batch", "batch_id", "removed_at"),
    comment="结汇批次的提单文件及装运口岸、目的口岸、装船日期",
    **table_options,
)

contracts = Table(
    "settlement_contracts",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="销售合同本地主键"),
    Column(
        "batch_id",
        ID,
        ForeignKey("settlement_batches.id", name="fk_settlement_contract_batch"),
        nullable=False,
        comment="所属结汇批次，指向 settlement_batches.id",
    ),
    Column("contract_no", identifier(100), nullable=False, comment="合同编号，即海关回执的出口合同号"),
    Column("contract_date", Date, nullable=False, comment="签订日期：最早出口日期往前推配置的天数"),
    Column("declaration_nos", JSON, nullable=False, comment="该合同覆盖的报关单号列表"),
    Column("buyer_party_id", ID, nullable=False, comment="买方抬头，指向 settlement_parties.id"),
    Column("seller_party_id", ID, nullable=False, comment="卖方抬头，指向 settlement_parties.id"),
    Column("trade_term", String(20), nullable=False, comment="成交方式，如 FOB"),
    Column("payment_terms_cn", String(300), nullable=False, comment="付款条件（中文）"),
    Column("payment_terms_en", String(300), nullable=False, comment="付款条件（英文）"),
    Column("port_of_loading", String(200), nullable=False, comment="装运口岸，取自提单"),
    Column("port_of_destination", String(200), nullable=False, comment="目的口岸，取自提单"),
    Column("currency", String(20), nullable=False, comment="币种，与批次一致"),
    Column("amount", Numeric(24, 6), nullable=False, comment="合同金额：该合同号下海关回执成交总价合计"),
    Column(
        "source_digest", CHAR(64), nullable=False, comment="生成时输入内容的 SHA-256，用于判断是否需重新生成"
    ),
    Column("file_id", identifier(36), nullable=False, comment="资料目录中的 PDF 文件标识"),
    Column("sha256", CHAR(64), nullable=False, comment="PDF 内容 SHA-256"),
    Column("size_bytes", Integer, nullable=False, comment="PDF 大小，字节"),
    Column("stamp_note", String(200), comment="盖章说明：未盖章的一方及原因；双方均已盖章为空"),
    Column("generated_by", String(190), nullable=False, comment="生成人（认证身份）"),
    Column("generated_at", TIMESTAMP, nullable=False, comment="生成时间，UTC"),
    *timestamps(),
    UniqueConstraint("batch_id", "contract_no", name="uq_settlement_contract_batch_no"),
    comment="结汇批次按模板生成的销售合同 PDF 及其生成依据",
    **table_options,
)

parties = Table(
    "settlement_parties",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="合同抬头本地主键"),
    Column("name", String(300), nullable=False, comment="匹配用名称；买方须与海关回执境外收货人一致"),
    Column("name_key", identifier(300), nullable=False, comment="名称规范化键（去空白、小写），唯一"),
    Column("name_cn", String(255), comment="合同上的中文名称"),
    Column("name_en", String(255), nullable=False, comment="合同上的英文名称"),
    Column("address_cn", String(500), comment="中文地址"),
    Column("address_en", String(500), nullable=False, comment="英文地址"),
    Column("phone", String(100), comment="电话"),
    Column("stamp_file_id", identifier(36), comment="印章图片文件标识；未上传为空"),
    Column("stamp_sha256", CHAR(64), comment="印章图片 SHA-256"),
    Column("stamp_extension", String(10), comment="印章图片扩展名：png 或 jpg"),
    Column("updated_by", String(190), nullable=False, comment="最近维护人（认证身份）"),
    *timestamps(),
    UniqueConstraint("name_key", name="uq_settlement_party_name_key"),
    comment="销售合同买卖双方抬头与印章",
    **table_options,
)

TABLES = (parties, bills, contracts)


def upgrade():
    for table in TABLES:
        table.create(op.get_bind())


def downgrade():
    bind = op.get_bind()
    # 结汇资料是提交银行的业务凭证，有数据时不允许降级删除。
    for table in () if op.get_context().as_sql else TABLES:
        if bind.execute(sa.select(sa.func.count()).select_from(table)).scalar():
            raise RuntimeError(f"{table.name} 已有结汇资料数据，拒绝自动降级；请管理员确认后手工处理")
    for table in reversed(TABLES):
        table.drop(bind)
