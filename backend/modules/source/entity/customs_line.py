"""报关明细。"""

from sqlalchemy import Boolean, Column, ForeignKey, Index, Numeric, String, Table, UniqueConstraint, text

from backend.core.schema import ID, schema_metadata, table_options, timestamps

customs_lines = Table(
    "source_customs_lines",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "customs_declaration_id",
        ID,
        ForeignKey("source_customs_declarations.id", name="fk_source_customs_line_head"),
        comment="报关单本地主键，指向 source_customs_declarations.id",
        nullable=False,
    ),
    Column(
        "source_line_key", String(190), comment="同一单据内的稳定来源行身份；与显示行号分开", nullable=False
    ),
    Column("line_no", String(40), comment="来源显示行号，不单独作为稳定业务身份"),
    Column("pl_no", String(100), comment="PL / Packing 编号，用于采购报关查询与关联"),
    Column("sales_order_no", String(150), comment="关联销售订单号"),
    Column(
        "company_id",
        ID,
        ForeignKey("source_companies.id", name="fk_source_customs_line_company"),
        comment="采购公司本地主键，指向 source_companies.id",
    ),
    Column("origin_place", String(255), comment="货源地"),
    Column("item_code", String(150), comment="来源商品编码"),
    Column("declaration_name", String(500), comment="报关品名，可能不同于采购或发票品名"),
    Column("specification", String(500), comment="商品规格型号"),
    Column("quantity", Numeric(26, 8), comment="该表所属业务口径的数量，与本行 unit 配套"),
    Column("unit", String(50), comment="该表所属业务口径的单位，与本行 quantity 配套"),
    Column(
        "declared_quantity", Numeric(26, 8), comment="报关数量；与 declared_unit 配套，不直接代替采购开票数量"
    ),
    Column("declared_unit", String(50), comment="报关数量单位"),
    Column("unit_price", Numeric(24, 8), comment="来源单价；税口径以对应来源映射为准，不能据此覆盖来源金额"),
    Column(
        "amount",
        Numeric(24, 6),
        comment="报关来源行金额，按配置映射；与本行 currency 配套，不能直接代替子采购应开含税金额",
    ),
    Column("currency", String(20), comment="业务币种代码，例如 CNY；不是汇率"),
    Column(
        "is_active",
        Boolean,
        comment="当前是否有效；停用保留历史记录，不物理删除",
        nullable=False,
        server_default=text("1"),
    ),
    *timestamps(),
    UniqueConstraint("customs_declaration_id", "source_line_key", name="uq_source_customs_line"),
    Index("ix_source_customs_line_pl", "pl_no"),
    comment="报关明细",
    **table_options,
)
