"""子采购行：开票单元。"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    text,
)

from backend.core.schema import ID, schema_metadata, table_options, timestamps

purchase_order_lines = Table(
    "source_purchase_order_lines",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "purchase_order_id",
        ID,
        ForeignKey("source_purchase_orders.id", name="fk_source_purchase_line_order"),
        comment="子采购单本地主键，指向 source_purchase_orders.id",
        nullable=False,
    ),
    Column(
        "source_line_key", String(190), comment="同一单据内的稳定来源行身份；与显示行号分开", nullable=False
    ),
    Column("line_no", String(40), comment="来源显示行号，不单独作为稳定业务身份"),
    Column("item_code", String(150), comment="来源商品编码"),
    Column("item_name", String(500), comment="商品名称原文"),
    Column("item_name_normalized", String(500), comment="规范化品名，用于比对"),
    Column("declaration_name", String(500), comment="报关品名，可能不同于采购或发票品名"),
    Column("specification", String(500), comment="商品规格型号"),
    Column("quantity", Numeric(26, 8), comment="子采购采购数量，是开票口径；与 unit 配套"),
    Column("unit", String(50), comment="采购单位，NS custrecord_swc_subpo_item_unit；未返回时为 NULL"),
    Column(
        "declared_quantity", Numeric(26, 8), comment="报关数量；与 declared_unit 配套，不直接代替采购开票数量"
    ),
    Column("declared_unit", String(50), comment="报关数量单位"),
    Column("unit_price", Numeric(24, 8), comment="子采购含税单价；NS ratewithrate 是单价，不是汇率"),
    Column("amount", Numeric(24, 6), comment="子采购行含税金额；来源缺失为 NULL，不得以零替代"),
    Column(
        "tax_rate",
        Numeric(8, 6),
        comment="税率小数（0.13 表示 13%），由 NS 税码显示名解析；无法解析或未返回时为 NULL",
    ),
    Column(
        "amount_status",
        String(24),
        comment="金额来源状态：matched 已取得；source_missing 来源缺失；不表示发票匹配通过",
        nullable=False,
        server_default="matched",
    ),
    Column(
        "parent_line_id",
        ID,
        ForeignKey("source_parent_order_lines.id", name="fk_source_purchase_line_parent"),
        comment="母采购行本地主键，指向 source_parent_order_lines.id",
    ),
    Column(
        "is_active",
        Boolean,
        comment="当前是否有效；停用保留历史记录，不物理删除",
        nullable=False,
        server_default=text("1"),
    ),
    *timestamps(),
    UniqueConstraint("purchase_order_id", "source_line_key", name="uq_source_purchase_line"),
    CheckConstraint("amount_status IN ('matched','source_missing')", name="ck_source_purchase_line_amount"),
    comment="子采购行：开票单元",
    **table_options,
)
