"""发票行。"""

from sqlalchemy import Column, ForeignKey, Numeric, String, Table, UniqueConstraint

from backend.core.schema import ID, schema_metadata, table_options, timestamps

items = Table(
    "invoice_items",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("invoice_id", ID, ForeignKey("invoice_headers.id", name="fk_invoice_item_header"), nullable=False),
    Column("source_line_key", String(190), nullable=False),
    Column("line_no", String(40)),
    Column("item_name", String(500)),
    Column("item_name_normalized", String(500)),
    Column("specification", String(500)),
    Column("quantity", Numeric(26, 8)),
    Column("unit", String(50)),
    Column("unit_price", Numeric(24, 8)),
    Column("amount_excluding_tax", Numeric(18, 2)),
    Column("tax_rate", Numeric(8, 6)),
    Column("tax_amount", Numeric(18, 2)),
    Column("amount_including_tax", Numeric(18, 2)),
    *timestamps(),
    UniqueConstraint("invoice_id", "source_line_key", name="uq_invoice_item"),
    comment="发票行",
    **table_options,
)
