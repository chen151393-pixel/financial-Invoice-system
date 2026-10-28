"""新增回写准备队列；只建新表，不触碰旧 NS 回写审计与锁。"""

from alembic import op
from backend.core.schema import ID, TIMESTAMP, table_options, timestamps
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)

revision = "0036_writeback_prepare"
down_revision = "0035_identity_member_selection"
branch_labels = None
depends_on = None
schema_metadata = MetaData()

tasks = Table(
    "writeback_tasks",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="回写任务主键"),
    Column("task_no", String(40), nullable=False, unique=True, comment="唯一任务编号"),
    Column("invoice_id", ID, nullable=False, comment="发票逻辑引用"),
    Column("fingerprint", String(64), nullable=False, comment="审核快照摘要"),
    Column("ns_account", String(100), nullable=False, comment="目标账套"),
    Column("vendor_id", String(20), nullable=False, comment="供应商内部编号"),
    Column("vendor_name", String(255), nullable=False, comment="供应商名称"),
    Column("invoice_no", String(100), nullable=False, comment="发票号码"),
    Column("amount", Numeric(18, 2), nullable=False, comment="整票含税金额"),
    Column("state", String(32), nullable=False, comment="准备任务状态"),
    Column("reason", String(500), nullable=False, comment="当前状态原因"),
    Column("historical", Boolean, nullable=False, comment="是否历史扫描入队"),
    Column("snapshot", JSON, nullable=False, comment="不可变审核快照"),
    Column("candidates", JSON, comment="最近完整候选查询结果"),
    Column("revision", Integer, nullable=False, comment="乐观并发版本"),
    Column("current_plan_id", ID, comment="当前目标方案逻辑引用"),
    Column("lease_token", String(36), comment="只读查询租约标识"),
    Column("lease_until", TIMESTAMP, comment="只读查询租约到期时间"),
    Column("next_query_at", TIMESTAMP, comment="下次只读查询时间"),
    Column("queried_at", TIMESTAMP, comment="最近完成查询时间"),
    *timestamps(),
    UniqueConstraint("invoice_id", "fingerprint", name="uq_writeback_invoice_snapshot"),
    Index("ix_writeback_queue", "ns_account", "state", "next_query_at"),
    comment="发票回写准备任务，不执行 NS 写操作",
    **table_options,
)

plans = Table(
    "writeback_plans",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="方案主键"),
    Column("task_id", ID, ForeignKey("writeback_tasks.id"), nullable=False, comment="所属准备任务"),
    Column("revision", Integer, nullable=False, comment="确认时任务版本"),
    Column("request_id", String(36), nullable=False, comment="幂等确认请求编号"),
    Column("request_hash", String(64), nullable=False, comment="确认正文与操作者摘要"),
    Column("body", JSON, nullable=False, comment="不可变目标和候选证据"),
    Column("confirmed_by", String(200), nullable=False, comment="确认身份"),
    *timestamps(),
    UniqueConstraint("task_id", "revision", name="uq_writeback_plan_revision"),
    UniqueConstraint("task_id", "request_id", name="uq_writeback_plan_request"),
    comment="仅追加的账单分配方案",
    **table_options,
)

audit = Table(
    "writeback_audit",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="审计主键"),
    Column("task_id", ID, ForeignKey("writeback_tasks.id"), nullable=False, comment="所属任务"),
    Column("action", String(40), nullable=False, comment="操作类型"),
    Column("actor", String(200), nullable=False, comment="操作身份"),
    Column("detail", JSON, nullable=False, comment="审计事实，不含密钥"),
    *timestamps(),
    comment="回写准备审计",
    **table_options,
)

invoice_guards = Table(
    "writeback_invoice_guards",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="整票指针主键"),
    Column("invoice_id", ID, nullable=False, unique=True, comment="唯一发票逻辑引用"),
    Column("task_id", ID, ForeignKey("writeback_tasks.id"), nullable=False, comment="当前任务"),
    *timestamps(),
    comment="同一发票当前准备任务",
    **table_options,
)


def upgrade():
    for table in schema_metadata.sorted_tables:
        table.create(op.get_bind(), checkfirst=False)


def downgrade():
    raise RuntimeError("准备任务可能已确认，不能降级删除审核与方案证据")
