"""母采购行。"""

from sqlalchemy import Boolean, Column, ForeignKey, Numeric, String, Table, UniqueConstraint, text

from backend.core.schema import ID, schema_metadata, table_options, timestamps

parent_order_lines = Table(
    "source_parent_order_lines",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column(
        "parent_order_id",
        ID,
        ForeignKey("source_parent_orders.id", name="fk_source_parent_line_order"),
        nullable=False,
    ),
    Column("source_line_key", String(190), nullable=False, comment="稳定行键 transactionline:<uniquekey>"),
    Column("line_no", String(40)),
    Column("item_code", String(150)),
    Column("item_name", String(500)),
    Column("declaration_name", String(500)),
    Column("specification", String(500)),
    Column("quantity", Numeric(26, 8)),
    Column("unit", String(50)),
    Column("unit_price", Numeric(24, 8)),
    Column("amount", Numeric(24, 6)),
    Column("is_active", Boolean, nullable=False, server_default=text("1")),
    *timestamps(),
    UniqueConstraint("parent_order_id", "source_line_key", name="uq_source_parent_line"),
    comment="母采购行",
    **table_options,
)
