"""子采购合同：只记录共享盘路径，数据库不保存文件内容。"""

from sqlalchemy import CHAR, CheckConstraint, Column, ForeignKey, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

documents = Table(
    "task_documents",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "task_id",
        ID,
        ForeignKey("task_tasks.id", name="fk_task_document_task"),
        comment="开票任务 ID，指向 task_tasks.id",
        nullable=False,
    ),
    Column(
        "purchase_order_id", ID, comment="子采购单本地主键，指向 source_purchase_orders.id", nullable=False
    ),
    Column("order_no", String(150), comment="采购单号，业务展示与检索用", nullable=False),
    Column("ns_environment", String(100), nullable=False, comment="合同下载使用的 NS 环境标识"),
    Column("ns_file_id", String(40), comment="NS 合同文件 ID"),
    Column("filename", String(255), comment="合同文件名"),
    Column("sha256", CHAR(64), comment="合同文件内容摘要，用于校验与防止静默覆盖"),
    Column("archive_path", String(2048), comment="合同共享盘路径；PDF 文件正文不存数据库"),
    Column(
        "status",
        String(24),
        comment="合同状态：pending 待归档；archived 已归档；failed 失败",
        nullable=False,
        server_default="pending",
    ),
    Column("error_message", String(500), comment="归档失败原因"),
    Column("archived_at", TIMESTAMP, comment="合同成功归档时间，UTC"),
    *timestamps(),
    UniqueConstraint("task_id", "purchase_order_id", name="uq_task_document"),
    CheckConstraint("status IN ('pending','archived','failed')", name="ck_task_document_status"),
    comment="子采购合同：只记录共享盘路径",
    **table_options,
)
