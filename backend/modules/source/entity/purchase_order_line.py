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
    Column("id", ID, primary_key=True, autoincrement=True),
    Column(
        "purchase_order_id",
        ID,
        ForeignKey("source_purchase_orders.id", name="fk_source_purchase_line_order"),
        nullable=False,
    ),
    Column("source_line_key", String(190), nullable=False),
    Column("line_no", String(40)),
    Column("item_code", String(150)),
    Column("item_name", String(500)),
    Column("item_name_normalized", String(500), comment="品名比对用"),
    Column("declaration_name", String(500), comment="报关品名"),
    Column("specification", String(500)),
    Column("quantity", Numeric(26, 8), comment="采购数量（开票口径）"),
    Column(
        "unit", String(50), comment="采购单位（开票口径），NS custrecord_swc_subpo_item_unit；未返回时为空"
    ),
    Column("declared_quantity", Numeric(26, 8), comment="报关数量，只用于报关核对"),
    Column("declared_unit", String(50)),
    Column("unit_price", Numeric(24, 8), comment="含税单价"),
    Column("amount", Numeric(24, 6), comment="含税金额；来源缺失时为空"),
    Column("amount_status", String(24), nullable=False, server_default="matched"),
    Column(
        "parent_line_id",
        ID,
        ForeignKey("source_parent_order_lines.id", name="fk_source_purchase_line_parent"),
    ),
    Column("is_active", Boolean, nullable=False, server_default=text("1")),
    *timestamps(),
    UniqueConstraint("purchase_order_id", "source_line_key", name="uq_source_purchase_line"),
    CheckConstraint("amount_status IN ('matched','source_missing')", name="ck_source_purchase_line_amount"),
    comment="子采购行：开票单元",
    **table_options,
)
