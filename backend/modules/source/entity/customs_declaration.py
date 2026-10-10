"""报关单。"""

from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    String,
    Table,
    UniqueConstraint,
    text,
)

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

customs_declarations = Table(
    "source_customs_declarations",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("ns_account", String(100), nullable=False),
    Column("ns_internal_id", String(190), nullable=False),
    Column("record_no", String(150), comment="CD 编号"),
    Column("declaration_no", String(150), comment="真实报关单号"),
    Column("declaration_date", Date),
    Column("declarant_company_id", ID, ForeignKey("source_companies.id", name="fk_source_customs_company")),
    Column("detail_status", String(24), nullable=False, server_default="pending"),
    Column(
        "relation_status",
        String(24),
        nullable=False,
        server_default="partial",
        comment="关联依据完整性：partial / complete；不是审核结论",
    ),
    Column("relation_issues", JSON, comment="关联依据不完整的原因列表"),
    Column("content_sha256", CHAR(64), comment="报关单 + 关联子采购的展示内容摘要，审核比对用"),
    Column("source_modified_at", TIMESTAMP),
    Column("synced_at", TIMESTAMP, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default=text("1")),
    Column("raw_record_id", ID, ForeignKey("source_raw_records.id", name="fk_source_customs_raw")),
    *timestamps(),
    UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_customs_ns"),
    Index("ix_source_customs_record", "ns_account", "record_no"),
    Index("ix_source_customs_number", "ns_account", "declaration_no"),
    CheckConstraint(
        "detail_status IN ('pending','complete','failed')", name="ck_source_customs_detail_status"
    ),
    CheckConstraint("relation_status IN ('partial','complete')", name="ck_source_customs_relation_status"),
    comment="报关单",
    **table_options,
)
