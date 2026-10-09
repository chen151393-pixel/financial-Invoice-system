"""现有回写审计表。"""

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Table

from backend.core.schema import identifier, metadata, table_options

audit = Table(
    "ns_audit",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("at", BigInteger, nullable=False),
    Column("actor", identifier(200), nullable=False),
    Column("action", String(32), nullable=False),
    Column("preview_id", identifier(36), ForeignKey("ns_previews.id"), nullable=False),
    **table_options,
)

finance_audit = Table(
    "finance_review_audit",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("at", BigInteger, nullable=False),
    Column("actor", identifier(200), nullable=False),
    Column(
        "snapshot_id", identifier(36), ForeignKey("finance_review_snapshots.id"), nullable=False, unique=True
    ),
    Column("note", String(300), nullable=False),
    **table_options,
)
