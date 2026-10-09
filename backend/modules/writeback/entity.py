"""回写预览与持久目标锁；保持既有表结构不变。"""

from sqlalchemy import BigInteger, Column, ForeignKey, Index, String, Table

from backend.core.schema import document, identifier, metadata, table_options

previews = Table(
    "ns_previews",
    metadata,
    Column("id", identifier(36), primary_key=True),
    Column("account", identifier(100), nullable=False),
    Column("owner", identifier(200), nullable=False),
    Column("target", identifier(255), nullable=False),
    Column("operation", String(16), nullable=False),
    Column("payload", document, nullable=False),
    Column("snapshot", document),
    Column("created_at", BigInteger, nullable=False),
    Column("expires", BigInteger, nullable=False),
    Column("state", String(16), nullable=False),
    Column("result", document),
    Index("ix_ns_previews_owner_created", "owner", "created_at"),
    **table_options,
)
# 用跨数据库唯一约束保护目标，不依赖SQLite专有索引。
target_locks = Table(
    "ns_target_locks",
    metadata,
    Column("account", identifier(100), primary_key=True),
    Column("target", identifier(255), primary_key=True),
    Column("preview_id", identifier(36), ForeignKey("ns_previews.id"), nullable=False, unique=True),
    **table_options,
)
