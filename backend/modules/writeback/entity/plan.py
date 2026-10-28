"""不可变目标方案版本。"""

from backend.core.schema import ID, schema_metadata, table_options, timestamps
from sqlalchemy import JSON, Column, ForeignKey, Integer, String, Table, UniqueConstraint

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
