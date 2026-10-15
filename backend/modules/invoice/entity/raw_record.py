"""柠檬云原始数据：内容不变不重复保存。"""

from sqlalchemy import CHAR, JSON, Column, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

raw_records = Table(
    "invoice_raw_records",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("source", String(24), nullable=False, comment="lemon_open2 / lemon_excel"),
    Column("lemon_account", String(100), nullable=False),
    Column("external_id", String(190), nullable=False, comment="API 记录 ID；Excel 为发票去重键"),
    Column("payload", JSON, nullable=False),
    Column("payload_sha256", CHAR(64), nullable=False),
    Column("fetched_at", TIMESTAMP, nullable=False),
    *timestamps(),
    UniqueConstraint(
        "source", "lemon_account", "external_id", "payload_sha256", name="uq_invoice_raw_content"
    ),
    comment="柠檬云原始数据",
    **table_options,
)
