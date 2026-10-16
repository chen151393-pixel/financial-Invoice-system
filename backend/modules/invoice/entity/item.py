"""发票行。"""

from sqlalchemy import Boolean, Column, ForeignKey, Numeric, String, Table, UniqueConstraint

from backend.core.schema import ID, schema_metadata, table_options, timestamps

items = Table(
    "invoice_items",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "invoice_id",
        ID,
        ForeignKey("invoice_headers.id", name="fk_invoice_item_header"),
        comment="本地发票 ID，指向 invoice_headers.id",
        nullable=False,
    ),
    Column(
        "source_line_key", String(190), comment="同一单据内的稳定来源行身份；与显示行号分开", nullable=False
    ),
    Column("line_no", String(40), comment="来源显示行号，不单独作为稳定业务身份"),
    Column("item_name", String(500), comment="商品名称原文"),
    Column("item_name_normalized", String(500), comment="规范化品名，用于比对"),
    Column("specification", String(500), comment="商品规格型号"),
    Column("quantity", Numeric(26, 8), comment="该表所属业务口径的数量，与本行 unit 配套"),
    Column("unit", String(50), comment="该表所属业务口径的单位，与本行 quantity 配套"),
    Column("unit_price", Numeric(24, 8), comment="来源单价；税口径以对应来源映射为准，不能据此覆盖来源金额"),
    Column("amount_excluding_tax", Numeric(18, 2), comment="不含税金额；票头为整票，商品行为该行"),
    Column("tax_rate", Numeric(8, 6), comment="税率小数，例如 0.13 表示 13%；不是单位换算比例"),
    Column("tax_amount", Numeric(18, 2), comment="税额；票头为整票，商品行为该行"),
    Column("amount_including_tax", Numeric(18, 2), comment="价税合计；票头为整票，商品行为该行"),
    Column(
        "is_active",
        Boolean,
        comment="当前是否有效；停用保留历史记录，不物理删除",
        nullable=False,
        server_default="1",
    ),
    *timestamps(),
    UniqueConstraint("invoice_id", "source_line_key", name="uq_invoice_item"),
    comment="发票行",
    **table_options,
)
