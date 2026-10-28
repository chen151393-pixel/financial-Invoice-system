"""整票当前任务指针。"""

from backend.core.schema import ID, schema_metadata, table_options, timestamps
from sqlalchemy import Column, ForeignKey, Table

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
