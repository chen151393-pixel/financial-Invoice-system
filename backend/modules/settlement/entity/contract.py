"""平台按模板生成的销售合同：一个批次内按出口合同号（销售订单号）各一份。

合同内容来自海关回执明细、提单口岸与公司抬头；source_digest 记录生成时的输入摘要，输入变化后须重新生成。
重新生成时整批替换本表记录，文件本体保存在结汇资料目录。
"""

from sqlalchemy import CHAR, JSON, Column, Date, ForeignKey, Integer, Numeric, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, identifier, schema_metadata, table_options, timestamps

settlement_contracts = Table(
    "settlement_contracts",
    schema_metadata,
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
