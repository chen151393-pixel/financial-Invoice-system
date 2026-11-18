"""直接收汇确认分配记录。"""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Numeric, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, identifier, schema_metadata, table_options

settlement_direct_allocations = Table(
    "settlement_direct_allocations",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("receipt_id", ID, ForeignKey("settlement_bank_receipts.id"), nullable=False),
    Column("bank_reference", String(200), nullable=False),
    Column("declaration_no", identifier(150), nullable=False),
    Column("amount", Numeric(24, 6), nullable=False),
    Column("request_id", String(36), nullable=False),
    Column("confirmed_at", TIMESTAMP, nullable=False),
    Column("confirmed_by", String(190), nullable=False),
    CheckConstraint("amount > 0", name="ck_settlement_direct_amount"),
    UniqueConstraint("request_id", "declaration_no", name="uq_settlement_direct_request_decl"),
    Index("ix_settlement_direct_receipt", "receipt_id"),
    Index("ix_settlement_direct_declaration", "declaration_no"),
    **table_options,
)
