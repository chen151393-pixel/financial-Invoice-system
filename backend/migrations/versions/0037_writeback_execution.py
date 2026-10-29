"""新增 NS 写入请求与账单目标锁；只建新表，不修改准备阶段四张表。"""

from alembic import op
from backend.core.schema import ID, TIMESTAMP, table_options, timestamps
from sqlalchemy import JSON, Boolean, Column, ForeignKey, MetaData, String, Table, UniqueConstraint

revision = "0037_writeback_execution"
down_revision = "0036_writeback_prepare"
branch_labels = None
depends_on = None
schema_metadata = MetaData()

# 外键所指的准备阶段表已由 0036 创建，这里只登记名称与主键供建表引用，不会重建。
Table("writeback_tasks", schema_metadata, Column("id", ID, primary_key=True))
Table("writeback_plans", schema_metadata, Column("id", ID, primary_key=True))

requests = Table(
    "writeback_requests",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="写入请求主键"),
    Column("task_id", ID, ForeignKey("writeback_tasks.id"), nullable=False, comment="所属回写任务"),
    Column(
        "plan_id", ID, ForeignKey("writeback_plans.id"), nullable=False, unique=True, comment="对应冻结方案"
    ),
    Column("request_id", String(36), nullable=False, unique=True, comment="发送 NS 的请求编号"),
    Column("payload", JSON, nullable=False, comment="发送 NS 的冻结正文"),
    Column("preview", JSON, nullable=False, comment="逐账单写前、本次与写后累计预览"),
    Column("needs_confirmation", Boolean, nullable=False, comment="账单累计与明细不一致，须人工确认预览"),
    Column("confirmed_by", String(200), comment="预览确认身份"),
    Column("confirmed_at", TIMESTAMP, comment="预览确认时间"),
    Column("state", String(32), nullable=False, comment="请求状态"),
    Column("result", JSON, comment="NS 返回结果或人工核实结论"),
    Column("ns_record_id", String(20), comment="NS 供应商发票记录内部 ID"),
    Column("sent_at", TIMESTAMP, comment="最近发送时间"),
    Column("finished_at", TIMESTAMP, comment="得到最终结果时间"),
    *timestamps(),
    comment="发票回写的 NS 写入请求",
    **table_options,
)

target_locks = Table(
    "writeback_target_locks",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="目标锁主键"),
    Column("ns_account", String(100), nullable=False, comment="目标账套"),
    Column("bill_id", String(20), nullable=False, comment="NS 供应商账单内部 ID"),
    Column("request_id", ID, ForeignKey("writeback_requests.id"), nullable=False, comment="持有锁的写入请求"),
    *timestamps(),
    UniqueConstraint("ns_account", "bill_id", name="uq_writeback_target_lock"),
    comment="回写目标账单持久锁",
    **table_options,
)


def upgrade():
    requests.create(op.get_bind(), checkfirst=False)
    target_locks.create(op.get_bind(), checkfirst=False)


def downgrade():
    raise RuntimeError("写入请求与目标锁是 NS 写入证据，不能降级删除")
