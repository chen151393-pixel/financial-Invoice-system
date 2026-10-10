"""子采购单。"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

purchase_orders = Table(
    "source_purchase_orders",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("ns_account", String(100), nullable=False),
    Column("ns_internal_id", String(190), nullable=False),
    Column("order_no", String(150), nullable=False, comment="子采购单号"),
    Column("order_date", Date),
    Column("pl_no", String(100)),
    Column("parent_order_id", ID, ForeignKey("source_parent_orders.id", name="fk_source_purchase_parent")),
    Column("parent_relation_status", String(24), nullable=False, server_default="unknown"),
    Column("supplier_id", ID, ForeignKey("source_suppliers.id", name="fk_source_purchase_supplier")),
    Column("company_id", ID, ForeignKey("source_companies.id", name="fk_source_purchase_company")),
    Column("currency", String(20)),
    Column("total_amount", Numeric(24, 6)),
    Column("detail_status", String(24), nullable=False, server_default="pending", comment="明细是否完整读取"),
    Column("source_modified_at", TIMESTAMP),
    Column("synced_at", TIMESTAMP, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default=text("1")),
    Column("raw_record_id", ID, ForeignKey("source_raw_records.id", name="fk_source_purchase_raw")),
    *timestamps(),
    Column("parent_order_no", String(150), comment="母采购单号（来源文本）"),
    UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_purchase_ns"),
    Index("ix_source_purchase_no", "ns_account", "order_no"),
    Index("ix_source_purchase_pl", "ns_account", "pl_no"),
    Index("ix_source_purchase_supplier", "supplier_id"),
    CheckConstraint(
        "parent_relation_status IN ('unknown','no_parent','linked')", name="ck_source_purchase_parent_status"
    ),
    CheckConstraint(
        "detail_status IN ('pending','complete','failed')", name="ck_source_purchase_detail_status"
    ),
    comment="子采购单",
    **table_options,
)
