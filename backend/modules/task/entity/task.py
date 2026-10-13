"""开票任务：审核通过后按 供应商 × 采购公司 × 币种 分组。"""

from sqlalchemy import CHAR, CheckConstraint, Column, Index, Integer, String, Table, UniqueConstraint, text

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

tasks = Table(
    "task_tasks",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("review_id", ID, nullable=False, comment="review_records.id"),
    Column("ns_account", String(100), nullable=False),
    Column("customs_declaration_id", ID, nullable=False, comment="冗余，便于按报关单查询"),
    Column("record_no", String(150), comment="冗余，CD 编号"),
    Column("supplier_id", ID),
    Column("company_id", ID),
    Column("currency", String(20)),
    Column(
        "group_key",
        CHAR(64),
        nullable=False,
        comment="供应商 + 公司 + 币种的分组键；身份缺失时按子采购单隔离",
    ),
    Column("status", String(24), nullable=False, server_default="documents_pending"),
    Column("completed_at", TIMESTAMP),
    *timestamps(),
    Column(
        "review_revision",
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="生成任务的审核版本",
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
