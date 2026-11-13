"""海关审核不可变记录。"""

from sqlalchemy import CHAR, Column, ForeignKey, Integer, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

customs_approvals = Table(
    "review_customs_approvals",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="本地自增主键"),
    Column("receipt_id", ID, ForeignKey("review_customs_receipts.id"), nullable=False, comment="海关回执 ID"),
    Column("receipt_revision", Integer, nullable=False, comment="审核时回执版本"),
    Column("receipt_sha256", CHAR(64), nullable=False, comment="审核时回执内容摘要"),
    Column("customs_declaration_id", ID, nullable=False, comment="来源报关单 ID，跨模块不建外键"),
    Column("source_sha256", CHAR(64), nullable=False, comment="审核时 NS 来源摘要"),
    Column("method", String(20), nullable=False, comment="auto 自动审核；manual 人工审核"),
    Column("approved_by", String(190), nullable=False, comment="审核人认证身份"),
    Column("approved_at", TIMESTAMP, nullable=False, comment="审核通过时间，UTC"),
    Column("note", String(300), comment="人工审核说明"),
    *timestamps(),
    UniqueConstraint(
        "receipt_id",
        "receipt_revision",
        "customs_declaration_id",
        "source_sha256",
        name="uq_review_customs_approval_version",
    ),
    comment="海关审核不可变版本",
    **table_options,
)
