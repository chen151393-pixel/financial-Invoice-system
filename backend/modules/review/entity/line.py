"""审核冻结的子采购行范围，不可修改。"""

from sqlalchemy import CHAR, Column, ForeignKey, Index, Numeric, String, Table, UniqueConstraint

from backend.core.schema import ID, schema_metadata, table_options, timestamps

lines = Table(
    "review_lines",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "review_id",
        ID,
        ForeignKey("review_records.id", name="fk_review_line_record"),
        comment="报关审核记录 ID，指向 review_records.id",
        nullable=False,
    ),
    Column(
        "purchase_order_id", ID, nullable=False, comment="子采购单本地主键，指向 source_purchase_orders.id"
    ),
    Column(
        "purchase_line_id",
        ID,
        nullable=False,
        comment="子采购明细 ID，指向 source_purchase_order_lines.id；开票业务围绕此身份组织",
    ),
    Column("customs_line_id", ID, comment="报关明细 ID，指向 source_customs_lines.id；未定位到行时可为空"),
    Column("supplier_id", ID, comment="供应商本地主键，指向 source_suppliers.id"),
    Column("company_id", ID, comment="采购公司本地主键，指向 source_companies.id"),
    Column("order_no", String(150), comment="采购单号，业务展示与检索用", nullable=False),
    Column("item_name", String(500), comment="商品名称原文"),
    Column("specification", String(500), comment="商品规格型号"),
    Column("currency", String(20), comment="业务币种代码，例如 CNY；不是汇率"),
    Column("quantity", Numeric(26, 8), comment="该表所属业务口径的数量，与本行 unit 配套"),
    Column("unit", String(50), comment="该表所属业务口径的单位，与本行 quantity 配套"),
    Column("amount", Numeric(24, 6), comment="审核冻结的应开含税金额；来源缺失保留 NULL"),
    Column("line_sha256", CHAR(64), nullable=False, comment="冻结时的子采购行内容摘要"),
    Column("purchase_basis_id", ID, comment="全局子采购行开票依据版本 ID，逻辑指向 review_purchase_bases.id"),
    *timestamps(),
    UniqueConstraint("review_id", "purchase_line_id", name="uq_review_line"),
    Index("ix_review_line_purchase", "purchase_line_id"),
    comment="审核冻结的子采购行范围，不可修改",
    **table_options,
)
