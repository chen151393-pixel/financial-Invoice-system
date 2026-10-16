"""NS 原始数据；内容变化时追加一行，主表指向最新一行。"""

from sqlalchemy import CHAR, JSON, Column, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

raw_records = Table(
    "source_raw_records",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column("ns_account", String(100), comment="NS 账套标识，用于隔离正式、沙箱等来源", nullable=False),
    Column(
        "record_type", String(100), nullable=False, comment="NS 原始记录类型；关联依据使用 relation_evidence"
    ),
    Column(
        "ns_internal_id",
        String(190),
        comment="NS 来源身份；与账套组合识别记录。公司身份可能带记录类型前缀",
        nullable=False,
    ),
    Column("payload", JSON, comment="未经业务投影的来源正文或关联依据 JSON，供追溯", nullable=False),
    Column(
        "payload_sha256", CHAR(64), comment="原始内容 SHA-256；相同来源身份及摘要不重复存储", nullable=False
    ),
    Column("fetched_at", TIMESTAMP, comment="取得该原始数据的时间，UTC", nullable=False),
    *timestamps(),
    UniqueConstraint(
        "ns_account", "record_type", "ns_internal_id", "payload_sha256", name="uq_source_raw_content"
    ),
    comment="NS 原始数据；内容变化时追加一行，主表指向最新一行",
    **table_options,
)
