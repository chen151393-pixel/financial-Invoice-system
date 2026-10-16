"""母采购单：同步时按子采购单关联读取单头（币种、汇率），子采购单币种取自这里。"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    text,
)

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

parent_orders = Table(
    "source_parent_orders",
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
    Column("ns_record_type", String(100), comment="NS 单据记录类型，母采购为 purchaseOrder", nullable=False),
    Column("order_no", String(150), comment="采购单号，业务展示与检索用"),
    Column("order_date", Date, comment="采购单业务日期"),
    Column(
        "supplier_id",
        ID,
        ForeignKey("source_suppliers.id", name="fk_source_parent_supplier"),
        comment="供应商本地主键，指向 source_suppliers.id",
    ),
    Column(
        "company_id",
        ID,
        ForeignKey("source_companies.id", name="fk_source_parent_company"),
        comment="采购公司本地主键，指向 source_companies.id",
    ),
    Column("currency", String(20), comment="业务币种代码，例如 CNY；不是汇率"),
    Column("total_amount", Numeric(24, 6), comment="来源单头的整单金额；不能与行金额重复累加"),
    Column("source_status", String(100), comment="NS 原始业务状态，与本系统审核、任务状态分开"),
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
        ForeignKey("source_raw_records.id", name="fk_source_parent_raw"),
        comment="对应原始数据版本 ID；source 表指向 source_raw_records，invoice 表指向 invoice_raw_records",
    ),
    Column("currency_internal_id", String(100), comment="NS 币种记录内部 ID，供追溯；与 CNY 等币种代码不同"),
    *timestamps(),
    Column(
        "exchange_rate", Numeric(28, 12), comment="母采购单的 NS exchangerate 汇率；当前只保存，不自动换汇"
    ),
    UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_parent_ns"),
    Index("ix_source_parent_no", "ns_account", "order_no"),
    comment="母采购单",
    **table_options,
)
