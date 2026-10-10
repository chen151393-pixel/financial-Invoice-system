"""报关单与子采购单的关联，支持多对多与行级。"""

from sqlalchemy import CheckConstraint, Column, Computed, ForeignKey, Index, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

customs_purchase_links = Table(
    "source_customs_purchase_links",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column(
        "customs_declaration_id",
        ID,
        ForeignKey("source_customs_declarations.id", name="fk_source_link_customs"),
        nullable=False,
    ),
    Column(
        "purchase_order_id",
        ID,
        ForeignKey("source_purchase_orders.id", name="fk_source_link_purchase"),
        nullable=False,
    ),
    Column(
        "customs_line_id",
        ID,
        ForeignKey("source_customs_lines.id", name="fk_source_link_customs_line"),
        comment="行级关系；只有单头级关系时为空",
    ),
    Column(
        "purchase_line_id",
        ID,
        ForeignKey("source_purchase_order_lines.id", name="fk_source_link_purchase_line"),
    ),
    Column("evidence", String(24), nullable=False, comment="ns_reference / ns_v3 / local_packing"),
    Column("status", String(24), nullable=False, server_default="active"),
    # 唯一约束中可空列用 0 代替，避免多个空值绕过唯一性。
    Column(
        "customs_line_key", ID, Computed("COALESCE(customs_line_id, 0)", persisted=True), comment="唯一约束用"
    ),
    Column(
        "purchase_line_key",
        ID,
        Computed("COALESCE(purchase_line_id, 0)", persisted=True),
        comment="唯一约束用",
    ),
    Column("synced_at", TIMESTAMP, nullable=False),
    *timestamps(),
    UniqueConstraint(
        "customs_declaration_id",
        "purchase_order_id",
        "customs_line_key",
        "purchase_line_key",
        name="uq_source_link",
    ),
    Index("ix_source_link_purchase", "purchase_order_id", "status"),
    Index("ix_source_link_purchase_line", "purchase_line_id"),
    CheckConstraint("evidence IN ('ns_reference','ns_v3','local_packing')", name="ck_source_link_evidence"),
    CheckConstraint("status IN ('active','stale')", name="ck_source_link_status"),
    comment="报关单与子采购单的关联，支持多对多与行级",
    **table_options,
)
