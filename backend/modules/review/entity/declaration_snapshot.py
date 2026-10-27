"""财务列表读模型；金额与逐行计算结果以十进制字符串保存在快照中。"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    String,
    Table,
    UniqueConstraint,
)

from backend.core.schema import ID, TIMESTAMP, document, schema_metadata, table_options, timestamps

declaration_snapshots = Table(
    "review_declaration_snapshots",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="财务查询快照本地主键"),
    Column("customs_declaration_id", ID, nullable=False, comment="来源报关单本地主键；跨模块不建外键"),
    Column(
        "ns_account",
        String(100),
        ForeignKey("review_calculation_jobs.ns_account", name="fk_review_snapshot_job"),
        nullable=False,
        comment="来源 NS 账套",
    ),
    Column("declaration_date", Date, comment="申报日期，用于稳定分页排序"),
    Column("review_status", String(24), nullable=False, comment="审核状态：pending 或 approved"),
    Column("source_changed", Boolean, nullable=False, comment="来源是否变化且需要重审"),
    Column("approved_at", TIMESTAMP, comment="有效审核时间，UTC；用于北京时间自然月统计"),
    Column("margin_alert", Boolean, nullable=False, comment="是否有报关行采购单价超出人民币容差"),
    Column("auto_eligible", Boolean, nullable=False, comment="是否满足自动审核预判条件；不代表自动批准"),
    Column("search_text", document, nullable=False, comment="CD、报关单号、PL、子采购单号和品名搜索文本"),
    Column(
        "payload", document, nullable=False, comment="完整展示快照 JSON；含逐行幅度、状态、原因和人民币单价"
    ),
    Column("calculated_at", TIMESTAMP, nullable=False, comment="后台计算时间，UTC"),
    *timestamps(),
    UniqueConstraint("customs_declaration_id", name="uq_review_snapshot_declaration"),
    CheckConstraint("review_status IN ('pending','approved')", name="ck_review_snapshot_status"),
    Index(
        "ix_review_snapshot_page", "ns_account", "review_status", "declaration_date", "customs_declaration_id"
    ),
    Index("ix_review_snapshot_margin", "ns_account", "review_status", "margin_alert"),
    Index("ix_review_snapshot_auto", "ns_account", "review_status", "auto_eligible"),
    comment="财务报关单查询快照，后台计算后原子更新，列表只读取本表",
    **table_options,
)
