"""母采购单（由内部快照导入填充；同步不写入）。"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    text,
)

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

parent_orders = Table(
    "source_parent_orders",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("ns_account", String(100), nullable=False),
    Column("ns_internal_id", String(190), nullable=False),
    Column("ns_record_type", String(100), nullable=False),
    Column("order_no", String(150)),
    Column("order_date", Date),
    Column("supplier_id", ID, ForeignKey("source_suppliers.id", name="fk_source_parent_supplier")),
    Column("company_id", ID, ForeignKey("source_companies.id", name="fk_source_parent_company")),
    Column("currency", String(20)),
    Column("total_amount", Numeric(24, 6)),
    Column("source_status", String(100), comment="NS 原始业务状态"),
    Column("source_modified_at", TIMESTAMP),
    Column("synced_at", TIMESTAMP, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default=text("1")),
    Column("raw_record_id", ID, ForeignKey("source_raw_records.id", name="fk_source_parent_raw")),
    *timestamps(),
    UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_parent_ns"),
    Index("ix_source_parent_no", "ns_account", "order_no"),
    comment="母采购单",
    **table_options,
)
