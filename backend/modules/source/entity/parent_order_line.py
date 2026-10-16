"""母采购行。"""

from sqlalchemy import Boolean, Column, ForeignKey, Numeric, String, Table, UniqueConstraint, text

from backend.core.schema import ID, schema_metadata, table_options, timestamps

parent_order_lines = Table(
    "source_parent_order_lines",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "parent_order_id",
        ID,
        ForeignKey("source_parent_orders.id", name="fk_source_parent_line_order"),
        comment="母采购单本地主键，指向 source_parent_orders.id",
        nullable=False,
    ),
    Column(
        "source_line_key", String(190), nullable=False, comment="同一单据内的稳定来源行身份；与显示行号分开"
    ),
    Column("line_no", String(40), comment="来源显示行号，不单独作为稳定业务身份"),
    Column("item_code", String(150), comment="来源商品编码"),
    Column("item_name", String(500), comment="商品名称原文"),
    Column("declaration_name", String(500), comment="报关品名，可能不同于采购或发票品名"),
    Column("specification", String(500), comment="商品规格型号"),
    Column("quantity", Numeric(26, 8), comment="该表所属业务口径的数量，与本行 unit 配套"),
    Column("unit", String(50), comment="该表所属业务口径的单位，与本行 quantity 配套"),
    Column("unit_price", Numeric(24, 8), comment="来源单价；税口径以对应来源映射为准，不能据此覆盖来源金额"),
    Column(
        "amount", Numeric(24, 6), comment="母采购来源行金额；当前明细写入未接入，税口径需以后续来源映射核实"
    ),
    Column(
        "is_active",
        Boolean,
        comment="当前是否有效；停用保留历史记录，不物理删除",
        nullable=False,
        server_default=text("1"),
    ),
    *timestamps(),
    UniqueConstraint("parent_order_id", "source_line_key", name="uq_source_parent_line"),
    comment="母采购行",
    **table_options,
)
