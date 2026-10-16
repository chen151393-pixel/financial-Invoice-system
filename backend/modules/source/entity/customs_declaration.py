"""报关单。"""

from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    String,
    Table,
    UniqueConstraint,
    text,
)

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

customs_declarations = Table(
    "source_customs_declarations",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column("ns_account", String(100), comment="NS 账套标识，用于隔离正式、沙箱等来源", nullable=False),
    Column(
        "ns_internal_id",
        String(190),
        comment="NS 来源身份；与账套组合识别记录。公司身份可能带记录类型前缀",
        nullable=False,
    ),
    Column("record_no", String(150), comment="NS 报关记录的 CD 编号，与真实海关报关单号不同"),
    Column("declaration_no", String(150), comment="真实报关单号"),
    Column("declaration_date", Date, comment="报关业务日期"),
    Column(
        "declarant_company_id",
        ID,
        ForeignKey("source_companies.id", name="fk_source_customs_company"),
        comment="申报主体本地主键，指向 source_companies.id；不等同于采购公司",
    ),
    Column(
        "detail_status",
        String(24),
        comment="明细完整性：pending 待补齐；complete 完整；failed 失败或身份待核实",
        nullable=False,
        server_default="pending",
    ),
    Column(
        "relation_status",
        String(24),
        nullable=False,
        server_default="partial",
        comment="关联依据完整性：partial 不完整；complete 完整；不代表财务审核通过",
    ),
    Column("relation_issues", JSON, comment="关联依据缺失或冲突的原因列表"),
    Column("content_sha256", CHAR(64), comment="报关单及关联子采购展示内容摘要，用于检测审核后来源变化"),
    Column("source_modified_at", TIMESTAMP, comment="来源系统修改时间，用于识别旧版本"),
    Column("synced_at", TIMESTAMP, comment="本次成功保存来源数据的时间，UTC", nullable=False),
    Column(
        "is_active",
        Boolean,
        comment="当前是否有效；停用保留历史记录，不物理删除",
        nullable=False,
        server_default=text("1"),
    ),
    Column(
        "raw_record_id",
        ID,
        ForeignKey("source_raw_records.id", name="fk_source_customs_raw"),
        comment="对应原始数据版本 ID；source 表指向 source_raw_records，invoice 表指向 invoice_raw_records",
    ),
    *timestamps(),
    UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_customs_ns"),
    Index("ix_source_customs_record", "ns_account", "record_no"),
    Index("ix_source_customs_number", "ns_account", "declaration_no"),
    CheckConstraint(
        "detail_status IN ('pending','complete','failed')", name="ck_source_customs_detail_status"
    ),
    CheckConstraint("relation_status IN ('partial','complete')", name="ck_source_customs_relation_status"),
    comment="报关单",
    **table_options,
)
