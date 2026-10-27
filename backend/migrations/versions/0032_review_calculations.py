"""review：后台申报幅度计算队列与数据库分页快照。"""

from alembic import op
from backend.core.schema import ID, TIMESTAMP, document, table_options, timestamps
from sqlalchemy import Boolean, CheckConstraint, Column, Date, ForeignKey, Integer, String, UniqueConstraint

revision = "0032_review_calculations"
down_revision = "0031_matching_invoice_files"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_calculation_jobs",
        Column("id", ID, primary_key=True, autoincrement=True, comment="计算队列本地主键"),
        Column("ns_account", String(100), nullable=False, comment="需要更新财务查询快照的 NS 账套"),
        Column("requested_revision", Integer, nullable=False, comment="同步或审核提交时递增的请求代次"),
        Column("completed_revision", Integer, nullable=False, server_default="0", comment="已原子发布的代次"),
        Column(
            "calculation_key", String(100), nullable=False, server_default="", comment="算法版本及人民币容差"
        ),
        Column("attempts", Integer, nullable=False, server_default="0", comment="当前代次连续失败次数"),
        Column("retry_at", TIMESTAMP, comment="失败后最早重试时间，UTC"),
        Column("last_error", String(300), nullable=False, server_default="", comment="计算失败的中文说明"),
        *timestamps(),
        UniqueConstraint("ns_account", name="uq_review_calculation_account"),
        CheckConstraint(
            "requested_revision >= completed_revision AND completed_revision >= 0",
            name="ck_review_calculation_revision",
        ),
        comment="财务后台计算队列，按账套合并请求并持久重试",
        **table_options,
    )
    op.create_table(
        "review_declaration_snapshots",
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
            "payload",
            document,
            nullable=False,
            comment="完整展示快照 JSON；含逐行幅度、状态、原因和人民币单价",
        ),
        Column("calculated_at", TIMESTAMP, nullable=False, comment="后台计算时间，UTC"),
        *timestamps(),
        UniqueConstraint("customs_declaration_id", name="uq_review_snapshot_declaration"),
        CheckConstraint("review_status IN ('pending','approved')", name="ck_review_snapshot_status"),
        comment="财务报关单查询快照，后台计算后原子更新，列表只读取本表",
        **table_options,
    )
    op.create_index(
        "ix_review_snapshot_page",
        "review_declaration_snapshots",
        ["ns_account", "review_status", "declaration_date", "customs_declaration_id"],
    )
    op.create_index(
        "ix_review_snapshot_margin",
        "review_declaration_snapshots",
        ["ns_account", "review_status", "margin_alert"],
    )
    op.create_index(
        "ix_review_snapshot_auto",
        "review_declaration_snapshots",
        ["ns_account", "review_status", "auto_eligible"],
    )
    op.create_table(
        "review_snapshot_suppliers",
        Column("id", ID, primary_key=True, autoincrement=True, comment="财务快照供应商关联主键"),
        Column(
            "declaration_id",
            ID,
            ForeignKey(
                "review_declaration_snapshots.customs_declaration_id", name="fk_review_supplier_snapshot"
            ),
            nullable=False,
            comment="财务快照对应的来源报关单 ID",
        ),
        Column("supplier_id", ID, nullable=False, comment="来源供应商 ID；跨模块不建外键"),
        Column("ns_account", String(100), nullable=False, comment="来源 NS 账套"),
        Column("name", String(500), nullable=False, comment="来源供应商名称快照"),
        *timestamps(),
        UniqueConstraint("declaration_id", "supplier_id", name="uq_review_snapshot_supplier"),
        comment="财务查询快照的供应商筛选投影",
        **table_options,
    )
    op.create_index(
        "ix_review_snapshot_supplier", "review_snapshot_suppliers", ["supplier_id", "declaration_id"]
    )


def downgrade():
    raise RuntimeError("财务计算队列与快照可能正在使用，不能降级删除；请保留数据")
