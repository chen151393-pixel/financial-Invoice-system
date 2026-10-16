"""不可变业务版本；仅允许修改生命周期。"""

from sqlalchemy import (
    CHAR,
    JSON,
    CheckConstraint,
    Column,
    Computed,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

bases = Table(
    "review_purchase_bases",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column("ns_account", String(100), comment="NS 账套标识，用于隔离正式、沙箱等来源", nullable=False),
    Column(
        "purchase_order_id", ID, comment="子采购单本地主键，指向 source_purchase_orders.id", nullable=False
    ),
    Column(
        "purchase_line_id",
        ID,
        comment="子采购明细 ID，指向 source_purchase_order_lines.id；开票业务围绕此身份组织",
        nullable=False,
    ),
    Column("revision", Integer, comment="同一业务对象的递增版本号；具体对象见唯一约束", nullable=False),
    Column(
        "status",
        String(24),
        comment="依据状态：active 当前；review_required 待重审；superseded 已替代",
        nullable=False,
    ),
    Column(
        "current_purchase_line_id",
        ID,
        Computed("CASE WHEN status <> 'superseded' THEN purchase_line_id END", persisted=True),
        comment="自动生成：未被 superseded 的依据取子采购行 ID；active 和 review_required 均占当前唯一位置",
    ),
    Column("supplier_id", ID, comment="供应商本地主键，指向 source_suppliers.id"),
    Column("company_id", ID, comment="采购公司本地主键，指向 source_companies.id"),
    Column("currency", String(20), comment="业务币种代码，例如 CNY；不是汇率"),
    Column("quantity", Numeric(26, 8), comment="该表所属业务口径的数量，与本行 unit 配套"),
    Column("unit", String(50), comment="该表所属业务口径的单位，与本行 quantity 配套"),
    Column("amount", Numeric(24, 6), comment="审核冻结的应开含税金额；来源缺失保留 NULL"),
    Column(
        "currency_source",
        String(24),
        comment="依据币种来源：parent_order 母单继承；manual_verified 人工有据核实；unresolved 待核实",
        nullable=False,
    ),
    Column(
        "source_sha256",
        CHAR(64),
        comment="冻结时子采购来源关键内容摘要；用于检查来源是否变化",
        nullable=False,
    ),
    Column(
        "basis_sha256",
        CHAR(64),
        comment="开票依据内容摘要，包含冻结值和相关核实证据；相同依据可复用",
        nullable=False,
    ),
    Column(
        "source_refs",
        JSON,
        comment="来源版本引用 JSON；当前保存 purchase_raw_record_id、currency_raw_record_id；历史回填另带缺证据原因",
        nullable=False,
    ),
    Column(
        "currency_evidence",
        JSON,
        comment="人工币种核实证据 JSON：reference 引用、note 说明、actor 操作者、at 时间、sourceSha256 来源摘要",
    ),
    Column(
        "origin_review_id",
        ID,
        comment="首次建立此依据的报关审核 ID，逻辑指向 review_records.id",
        nullable=False,
    ),
    Column("approved_by", String(200), comment="审核通过的认证操作者", nullable=False),
    Column("approved_at", TIMESTAMP, comment="审核通过时间，UTC", nullable=False),
    *timestamps(),
    UniqueConstraint("purchase_line_id", "revision", name="uq_review_basis_revision"),
    UniqueConstraint("current_purchase_line_id", name="uq_review_basis_current"),
    Index("ix_review_basis_order", "purchase_order_id"),
    CheckConstraint("status IN ('active','review_required','superseded')", name="ck_review_basis_status"),
    comment="全局开票依据版本",
    **table_options,
)
