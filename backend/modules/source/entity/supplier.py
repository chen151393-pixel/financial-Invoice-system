"""供应商（NS vendor）。"""

from sqlalchemy import Boolean, Column, Index, String, Table, UniqueConstraint, text

from backend.core.schema import ID, schema_metadata, table_options, timestamps

suppliers = Table(
    "source_suppliers",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("ns_account", String(100), nullable=False),
    Column("ns_internal_id", String(190), nullable=False),
    Column("name", String(255), nullable=False),
    Column("name_normalized", String(255), nullable=False, comment="名称比对用"),
    Column("is_active", Boolean, nullable=False, server_default=text("1")),
    *timestamps(),
    UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_supplier_ns"),
    Index("ix_source_supplier_name", "ns_account", "name_normalized"),
    comment="供应商（NS vendor）",
    **table_options,
)
