"""只读准备任务；审核快照创建后不修改。"""

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps
from sqlalchemy import JSON, Boolean, Column, Index, Integer, Numeric, String, Table, UniqueConstraint

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
