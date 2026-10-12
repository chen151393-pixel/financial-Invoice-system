"""审核记录：一次审核通过一行，不可修改，全部行即审核历史。"""

from sqlalchemy import CHAR, CheckConstraint, Column, Computed, Integer, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

records = Table(
    "review_records",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("ns_account", String(100), nullable=False),
    Column("customs_declaration_id", ID, nullable=False, comment="source_customs_declarations.id"),
    Column("record_no", String(150), comment="冗余，CD 编号"),
    Column("revision", Integer, nullable=False, comment="同一报关单第几次审核"),
    Column("content_sha256", CHAR(64), nullable=False, comment="审核时看到的内容摘要"),
    Column("status", String(24), nullable=False, server_default="active"),
    Column("approved_by", String(200), nullable=False),
    Column("approved_at", TIMESTAMP, nullable=False),
    Column("note", String(300)),
    Column(
        "active_declaration_id",
        ID,
        Computed("CASE WHEN status = 'active' THEN customs_declaration_id END", persisted=True),
        comment="一张报关单只有一条有效审核",
    ),
    *timestamps(),
    UniqueConstraint("customs_declaration_id", "revision", name="uq_review_revision"),
    UniqueConstraint("active_declaration_id", name="uq_review_active"),
    CheckConstraint("status IN ('active','superseded')", name="ck_review_status"),
    comment="审核记录：一次审核通过一行，不可修改，全部行即审核历史",
    **table_options,
)
