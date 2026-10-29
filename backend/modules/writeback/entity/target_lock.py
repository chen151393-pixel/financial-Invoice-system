"""按 NS 账单的持久写入锁；结果不明或部分完成时保留，人工核实后释放。"""

from backend.core.schema import ID, schema_metadata, table_options, timestamps
from sqlalchemy import Column, ForeignKey, String, Table, UniqueConstraint

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
