"""不可变业务版本；仅允许修改生命周期。"""

from sqlalchemy import CHAR, JSON, Column, ForeignKey, Index, Integer, String, Table, UniqueConstraint

from backend.core.schema import ID, schema_metadata, table_options, timestamps

versions = Table(
    "invoice_versions",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "invoice_id",
        ID,
        ForeignKey("invoice_headers.id", name="fk_invoice_version_header"),
        comment="本地发票 ID，指向 invoice_headers.id",
        nullable=False,
    ),
    Column("revision", Integer, comment="同一业务对象的递增版本号；具体对象见唯一约束", nullable=False),
    Column(
        "content_sha256",
        CHAR(64),
        comment="规范化票头与明细的业务内容摘要，用于识别发票版本变化",
        nullable=False,
    ),
    Column("raw_record_id", ID, comment="生成此版本的发票原始记录 ID，逻辑指向 invoice_raw_records.id"),
    Column(
        "source",
        String(40),
        comment="来源渠道：lemon_excel 柠檬云 Excel；lemon_open2 柠檬云接口（待接入）",
        nullable=False,
    ),
    Column("external_id", String(255), comment="生成该版本的外部身份；当前 Excel 使用发票去重键"),
    Column(
        "currency_source",
        String(24),
        comment="发票币种来源：source_rule 来源规则；unresolved 历史来源待核实",
        nullable=False,
    ),
    Column(
        "source_rule_version", String(40), comment="来源适配规则版本；当前人民币 Excel 规则为 lemon_cny_v1"
    ),
    Column(
        "header_snapshot", JSON, comment="该版本票头 JSON 快照，含票面状态、币种和完整性等", nullable=False
    ),
    Column(
        "items_snapshot",
        JSON,
        comment="该版本全部商品行 JSON 快照，保存逻辑行 ID；精确小数用字符串",
        nullable=False,
    ),
    *timestamps(),
    UniqueConstraint("invoice_id", "revision", name="uq_invoice_version_revision"),
    Index("ix_invoice_version_content", "invoice_id", "content_sha256"),
    comment="发票不可变业务版本",
    **table_options,
)
