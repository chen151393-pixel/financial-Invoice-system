"""子采购合同：只记录共享盘路径，数据库不保存文件内容。"""

from sqlalchemy import CHAR, CheckConstraint, Column, ForeignKey, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

documents = Table(
    "task_documents",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("task_id", ID, ForeignKey("task_tasks.id", name="fk_task_document_task"), nullable=False),
    Column("purchase_order_id", ID, nullable=False),
    Column("order_no", String(150), nullable=False),
    Column("ns_environment", String(100), nullable=False, comment="合同下载的 NS 环境"),
    Column("ns_file_id", String(40)),
    Column("filename", String(255)),
    Column("sha256", CHAR(64)),
    Column("archive_path", String(2048), comment="共享盘路径；数据库不保存文件内容"),
    Column("status", String(24), nullable=False, server_default="pending"),
    Column("error_message", String(500)),
    Column("archived_at", TIMESTAMP),
    *timestamps(),
    UniqueConstraint("task_id", "purchase_order_id", name="uq_task_document"),
    CheckConstraint("status IN ('pending','archived','failed')", name="ck_task_document_status"),
    comment="子采购合同：只记录共享盘路径",
    **table_options,
)
