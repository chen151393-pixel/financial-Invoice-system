"""开票任务：审核通过后按 供应商 × 采购公司 × 币种 分组。"""

from sqlalchemy import (
    CHAR,
    JSON,
    CheckConstraint,
    Column,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    text,
)

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

tasks = Table(
    "task_tasks",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column("review_id", ID, nullable=False, comment="报关审核记录 ID，指向 review_records.id"),
    Column("ns_account", String(100), comment="NS 账套标识，用于隔离正式、沙箱等来源", nullable=False),
    Column(
        "customs_declaration_id",
        ID,
        nullable=False,
        comment="报关单本地主键，指向 source_customs_declarations.id",
    ),
    Column("record_no", String(150), comment="NS 报关记录的 CD 编号，与真实海关报关单号不同"),
    Column("supplier_id", ID, comment="供应商本地主键，指向 source_suppliers.id"),
    Column("company_id", ID, comment="采购公司本地主键，指向 source_companies.id"),
    Column("currency", String(20), comment="业务币种代码，例如 CNY；不是汇率"),
    Column(
        "group_key",
        CHAR(64),
        nullable=False,
        comment="供应商 × 采购公司 × 币种的分组摘要；身份缺失时按子采购单隔离",
    ),
    Column(
        "status",
        String(24),
        comment="任务状态：documents_pending 待合同；notify_pending 待通知；awaiting_invoice 等待开票；partially_received 部分收票；completed 完成；superseded 已替代",
        nullable=False,
        server_default="documents_pending",
    ),
    Column(
        "completed_at", TIMESTAMP, comment="任务完成时间；后续撤销或失效可使任务回退，历史另见 task_events"
    ),
    Column(
        "predecessor_task_ids", JSON, comment="前驱任务 ID 数组；依据变化后用新任务承接历史，不覆盖旧任务"
    ),
    *timestamps(),
    Column(
        "review_revision",
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="生成任务时的报关审核版本号",
    ),
    UniqueConstraint("review_id", "group_key", name="uq_task_review_group"),
    Index("ix_task_status_supplier", "status", "supplier_id"),
    Index("ix_task_declaration", "customs_declaration_id"),
    CheckConstraint(
        "status IN ('documents_pending','notify_pending','awaiting_invoice',"
        "'partially_received','completed','superseded')",
        name="ck_task_status",
    ),
    comment="开票任务：审核通过后按 供应商 × 采购公司 × 币种 分组",
    **table_options,
)
