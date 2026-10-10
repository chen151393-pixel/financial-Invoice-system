"""报关明细。"""

from sqlalchemy import Boolean, Column, ForeignKey, Index, Numeric, String, Table, UniqueConstraint, text

from backend.core.schema import ID, schema_metadata, table_options, timestamps

customs_lines = Table(
    "source_customs_lines",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column(
        "customs_declaration_id",
        ID,
        ForeignKey("source_customs_declarations.id", name="fk_source_customs_line_head"),
        nullable=False,
    ),
    Column("source_line_key", String(190), nullable=False),
    Column("line_no", String(40)),
    Column("pl_no", String(100)),
    Column("sales_order_no", String(150)),
    Column("company_id", ID, ForeignKey("source_companies.id", name="fk_source_customs_line_company")),
    Column("origin_place", String(255)),
    Column("item_code", String(150)),
    Column("declaration_name", String(500)),
    Column("specification", String(500)),
    Column("quantity", Numeric(26, 8)),
    Column("unit", String(50)),
    Column("declared_quantity", Numeric(26, 8)),
    Column("declared_unit", String(50)),
    Column("unit_price", Numeric(24, 8)),
    Column("amount", Numeric(24, 6)),
    Column("currency", String(20)),
    Column("is_active", Boolean, nullable=False, server_default=text("1")),
    *timestamps(),
    UniqueConstraint("customs_declaration_id", "source_line_key", name="uq_source_customs_line"),
    Index("ix_source_customs_line_pl", "pl_no"),
    comment="报关明细",
    **table_options,
)
