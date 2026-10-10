"""审核审计表，以及保留的历史回写表。

NS 回写代码已移至 archive/writeback 分支。ns_previews、ns_target_locks、ns_audit 的表和数据保留：
定义仍登记在元数据中，供迁移结构核验和历史应用库导入原样复制 executing/unknown 记录及其锁。
主线不再有代码读写这三张表；删除前须人工确认没有 executing/unknown 记录，再单独迁移删除。
"""

from sqlalchemy import BigInteger, Column, ForeignKey, Index, Integer, String, Table

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
target_locks = Table(
    "ns_target_locks",
    metadata,
    Column("account", identifier(100), primary_key=True),
    Column("target", identifier(255), primary_key=True),
    Column("preview_id", identifier(36), ForeignKey("ns_previews.id"), nullable=False, unique=True),
    **table_options,
)

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
