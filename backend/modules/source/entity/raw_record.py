"""NS 原始数据；内容变化时追加一行，主表指向最新一行。"""

from sqlalchemy import CHAR, JSON, Column, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

raw_records = Table(
    "source_raw_records",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("ns_account", String(100), nullable=False),
    Column("record_type", String(100), nullable=False, comment="NS 记录类型；关联依据为 relation_evidence"),
    Column("ns_internal_id", String(190), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("payload_sha256", CHAR(64), nullable=False),
    Column("fetched_at", TIMESTAMP, nullable=False),
    *timestamps(),
    UniqueConstraint(
        "ns_account", "record_type", "ns_internal_id", "payload_sha256", name="uq_source_raw_content"
    ),
    comment="NS 原始数据；内容变化时追加一行，主表指向最新一行",
    **table_options,
)
