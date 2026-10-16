"""开票任务属于审核后的跟进；来源快照不可变，旧版本保留供追溯。"""

from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGBLOB

from backend.core.schema import document, identifier, metadata, table_options

tasks = Table(
    "finance_invoice_tasks",
    metadata,
    Column("id", identifier(36), primary_key=True),
    Column("owner", identifier(200), nullable=False),
    Column("account", identifier(100), nullable=False),
    Column("declaration_id", identifier(190), nullable=False),
    Column("snapshot_id", identifier(36), ForeignKey("finance_review_snapshots.id"), nullable=False),
    Column("review_revision", Integer, nullable=False),
    Column("group_key", identifier(64), nullable=False),
    Column("supplier_key", identifier(64), nullable=False),
    Column("declaration_key", identifier(64), nullable=False),
    Column("supplier", String(255), nullable=False),
    Column("company", String(255), nullable=False),
    Column("currency", String(20), nullable=False),
    Column("record_number", String(190), nullable=False),
    Column("status", identifier(30), nullable=False),
    Column("payload", document, nullable=False),
    Column("created_at", BigInteger, nullable=False),
    UniqueConstraint("snapshot_id", "group_key", name="uq_finance_task_snapshot_group"),
    Index("ix_finance_task_owner_status", "owner", "status"),
    Index("ix_finance_task_review", "owner", "account", "declaration_id"),
    **table_options,
)

documents = Table(
    "finance_task_documents",
    metadata,
    Column("task_id", identifier(36), ForeignKey("finance_invoice_tasks.id"), primary_key=True),
    Column("order_id", identifier(190), primary_key=True),
    Column("environment", identifier(100), nullable=False),
    Column("ns_id", identifier(40), nullable=False),
    Column("filename", String(255), nullable=False),
    Column("sha256", identifier(64), nullable=False),
    # 新合同只留元数据；该列保留旧版原件，不删除历史副本。
    Column("content", LargeBinary().with_variant(LONGBLOB(), "mysql")),
    Column("downloaded_at", BigInteger, nullable=False),
    Column("archive_path", String(2048)),
    Column("archived_at", BigInteger),
    **table_options,
)

notifications = Table(
    "finance_task_notifications",
    metadata,
    Column("task_id", identifier(36), ForeignKey("finance_invoice_tasks.id"), primary_key=True),
    Column("revision", Integer, primary_key=True),
    Column("actor", identifier(200), nullable=False),
    Column("created_at", BigInteger, nullable=False),
    Column("payload", document, nullable=False),
    **table_options,
)
