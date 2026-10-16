"""子采购单。"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

purchase_orders = Table(
    "source_purchase_orders",
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
    Column("order_no", String(150), nullable=False, comment="采购单号，业务展示与检索用"),
    Column("order_date", Date, comment="采购单业务日期"),
    Column("pl_no", String(100), comment="PL / Packing 编号，用于采购报关查询与关联"),
    Column(
        "parent_order_id",
        ID,
        ForeignKey("source_parent_orders.id", name="fk_source_purchase_parent"),
        comment="母采购单本地主键，指向 source_parent_orders.id",
    ),
    Column(
        "parent_relation_status",
        String(24),
        comment="母单关系：unknown 待查明；no_parent 已确认无母单；linked 已关联",
        nullable=False,
        server_default="unknown",
    ),
    Column(
        "supplier_id",
        ID,
        ForeignKey("source_suppliers.id", name="fk_source_purchase_supplier"),
        comment="供应商本地主键，指向 source_suppliers.id",
    ),
    Column(
        "company_id",
        ID,
        ForeignKey("source_companies.id", name="fk_source_purchase_company"),
        comment="采购公司本地主键，指向 source_companies.id",
    ),
    Column("currency", String(20), comment="业务币种代码，例如 CNY；不是汇率"),
    Column("total_amount", Numeric(24, 6), comment="来源单头的整单金额；不能与行金额重复累加"),
    Column(
        "detail_status",
        String(24),
        nullable=False,
        server_default="pending",
        comment="明细完整性：pending 待补齐；complete 完整；failed 失败或身份待核实",
    ),
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
        ForeignKey("source_raw_records.id", name="fk_source_purchase_raw"),
        comment="对应原始数据版本 ID；source 表指向 source_raw_records，invoice 表指向 invoice_raw_records",
    ),
    Column(
        "currency_raw_record_id",
        ID,
        comment="继承币种所依据的母采购原始快照 ID，逻辑指向 source_raw_records.id",
    ),
    *timestamps(),
    Column("parent_order_no", String(150), comment="来源提供的母采购单号文本；与母单本地主键分开"),
    Column(
        "currency_source",
        String(24),
        nullable=False,
        server_default="unresolved",
        comment="币种来源：parent_order 母单继承；unresolved 待核实",
    ),
    Column("currency_issue", String(300), comment="币种待核实原因"),
    UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_purchase_ns"),
    Index("ix_source_purchase_no", "ns_account", "order_no"),
    Index("ix_source_purchase_pl", "ns_account", "pl_no"),
    Index("ix_source_purchase_supplier", "supplier_id"),
    CheckConstraint(
        "parent_relation_status IN ('unknown','no_parent','linked')", name="ck_source_purchase_parent_status"
    ),
    CheckConstraint(
        "detail_status IN ('pending','complete','failed')", name="ck_source_purchase_detail_status"
    ),
    CheckConstraint(
        "currency_source IN ('parent_order','unresolved')", name="ck_source_purchase_currency_source"
    ),
    comment="子采购单",
    **table_options,
)
