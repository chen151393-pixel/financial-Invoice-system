"""审核通过后持久登记的合同归档队列。"""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, String, Table, UniqueConstraint

from backend.core.schema import ID, schema_metadata, table_options, timestamps

contract_jobs = Table(
    "task_contract_jobs",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="合同归档作业主键"),
    Column(
        "task_id",
        ID,
        ForeignKey("task_tasks.id", name="fk_task_contract_job_task"),
        nullable=False,
        comment="开票任务 ID",
    ),
    Column("purchase_order_id", ID, nullable=False, comment="子采购单 ID，不建立跨模块外键"),
    Column("actor", String(190), nullable=False, comment="触发自动归档的财务审核身份"),
    Column(
        "status",
        String(20),
        nullable=False,
        server_default="pending",
        comment="pending待处理；completed已归档；failed失败待人工重试",
    ),
    Column("error_message", String(500), comment="脱敏失败原因，成功后清空"),
    *timestamps(),
    UniqueConstraint("task_id", "purchase_order_id", name="uq_task_contract_job"),
    CheckConstraint("status IN ('pending','completed','failed')", name="ck_task_contract_job_status"),
    Index("ix_task_contract_job_pending", "status", "id"),
    comment="财务审核提交后的合同自动归档队列，不保存 PDF",
    **table_options,
)
