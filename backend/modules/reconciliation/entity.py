"""审核预览不可变；审核结果按账户、身份及报关单隔离。"""

from sqlalchemy import BigInteger, Column, ForeignKey, Index, Integer, String, Table

from backend.core.schema import document, identifier, metadata, table_options

snapshots = Table(
    "finance_review_snapshots",
    metadata,
    Column("id", identifier(36), primary_key=True),
    Column("owner", identifier(200), nullable=False),
    Column("account", identifier(100), nullable=False),
    Column("declaration_id", identifier(190), nullable=False),
    Column("digest", identifier(64), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("payload", document, nullable=False),
    Column("created_at", BigInteger, nullable=False),
    Column("expires_at", BigInteger, nullable=False),
    Index("ix_finance_snapshot_owner_created", "owner", "created_at"),
    **table_options,
)
reviews = Table(
    "finance_reviews",
    metadata,
    Column("owner", identifier(200), primary_key=True),
    Column("account", identifier(100), primary_key=True),
    Column("declaration_id", identifier(190), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("snapshot_id", identifier(36), ForeignKey("finance_review_snapshots.id")),
    Column("digest", identifier(64)),
    Column("reviewed_at", BigInteger),
    Column("reviewed_by", identifier(200)),
    Column("note", String(300)),
    **table_options,
)
