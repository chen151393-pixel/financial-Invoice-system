"""准备阶段审计。"""

from backend.core.schema import ID, schema_metadata, table_options, timestamps
from sqlalchemy import JSON, Column, ForeignKey, String, Table

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
