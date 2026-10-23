"""报关资料：报关单、销售合同、发票，按报关单各下载一份，同一报关单的各供应商任务共用。"""

from sqlalchemy import JSON, CheckConstraint, Column, Index, Integer, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

DOC_TYPES = ("customs_declaration", "sales_contract", "invoice")

declaration_documents = Table(
    "task_declaration_documents",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="报关资料记录主键"),
    Column(
        "customs_declaration_id",
        ID,
        nullable=False,
        comment="报关单本地主键，指向 source_customs_declarations.id",
    ),
    Column("ns_account", String(100), nullable=False, comment="NS 账套标识"),
    Column("record_no", String(150), comment="报关单 CD 编号，下载时按此在 NS 重新定位"),
    Column(
        "doc_type",
        String(30),
        nullable=False,
        comment="资料类型：customs_declaration 报关单；sales_contract 销售合同；invoice 发票",
    ),
    Column(
        "status",
        String(20),
        nullable=False,
        server_default="pending",
        comment="pending 待下载；archived 已保存到共享盘；failed 失败待人工重试",
    ),
    Column("files", JSON, comment="已归档文件列表 [{filename, sha256, path}]；文件正文不存数据库"),
    Column("ns_id", String(40), comment="下载环境中的报关单内部 ID"),
    Column("error_message", String(500), comment="脱敏失败原因，成功后清空"),
    Column("requested_by", String(200), nullable=False, comment="最近一次登记或人工重试的认证身份"),
    Column("attempts", Integer, nullable=False, server_default="0", comment="已尝试下载次数"),
    Column("archived_at", TIMESTAMP, comment="最近一次成功归档时间，UTC"),
    *timestamps(),
    UniqueConstraint("customs_declaration_id", "doc_type", name="uq_task_declaration_document"),
    CheckConstraint(
        "doc_type IN ('customs_declaration','sales_contract','invoice')", name="ck_task_declaration_doc_type"
    ),
    CheckConstraint("status IN ('pending','archived','failed')", name="ck_task_declaration_doc_status"),
    Index("ix_task_declaration_doc_status", "status", "id"),
    comment="报关资料下载与归档记录（报关单、销售合同、发票），不保存 PDF",
    **table_options,
)
