"""柠檬云原始数据：内容不变不重复保存。"""

from sqlalchemy import CHAR, JSON, Column, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

raw_records = Table(
    "invoice_raw_records",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "source",
        String(24),
        nullable=False,
        comment="来源渠道：lemon_excel 柠檬云 Excel；lemon_open2 柠檬云接口（待接入）",
    ),
    Column(
        "lemon_account",
        String(100),
        comment="柠檬云来源账套命名空间；当前 Excel 固定为 lemon，不能直接视为任意 API 账套",
        nullable=False,
    ),
    Column(
        "external_id",
        String(190),
        nullable=False,
        comment="外部来源记录 ID；原始 Excel 记录使用发票去重键，票头 API ID 可为空",
    ),
    Column("payload", JSON, comment="未经业务投影的来源正文或关联依据 JSON，供追溯", nullable=False),
    Column(
        "payload_sha256", CHAR(64), comment="原始内容 SHA-256；相同来源身份及摘要不重复存储", nullable=False
    ),
    Column("fetched_at", TIMESTAMP, comment="取得该原始数据的时间，UTC", nullable=False),
    *timestamps(),
    UniqueConstraint(
        "source", "lemon_account", "external_id", "payload_sha256", name="uq_invoice_raw_content"
    ),
    comment="柠檬云原始数据",
    **table_options,
)
