"""task：报关资料与回签合同归档记录；任务新增 documents_incomplete（发票已收齐、资料待补齐）。

2026-10-23 业务确认：报关单、销售合同、发票由 NS 下载，回签合同人工上传；
子采购合同、报关资料、回签合同全部到齐且发票收齐，任务才完结。
"""

from alembic import op
from backend.core.schema import ID, TIMESTAMP, table_options, timestamps
from sqlalchemy import CHAR, JSON, CheckConstraint, Column, Index, Integer, String, UniqueConstraint

revision = "0028_task_document_completion"
down_revision = "0027_source_customs_created_at"
branch_labels = None
depends_on = None

NEW_STATUSES = (
    "('documents_pending','notify_pending','awaiting_invoice','partially_received',"
    "'documents_incomplete','completed','superseded')"
)
OLD_COMMENT = (
    "任务状态：documents_pending 待合同；notify_pending 待通知；awaiting_invoice 等待开票；"
    "partially_received 部分收票；completed 完成；superseded 已替代"
)
NEW_COMMENT = (
    "任务状态：documents_pending 待合同；notify_pending 待通知；awaiting_invoice 等待开票；"
    "partially_received 部分收票；documents_incomplete 发票已收齐、资料待补齐；completed 完成；superseded 已替代"
)


def upgrade():
    op.create_table(
        "task_declaration_documents",
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
            "doc_type IN ('customs_declaration','sales_contract','invoice')",
            name="ck_task_declaration_doc_type",
        ),
        CheckConstraint("status IN ('pending','archived','failed')", name="ck_task_declaration_doc_status"),
        Index("ix_task_declaration_doc_status", "status", "id"),
        comment="报关资料下载与归档记录（报关单、销售合同、发票），不保存 PDF",
        **table_options,
    )
    op.create_table(
        "task_signed_contracts",
        Column("id", ID, primary_key=True, autoincrement=True, comment="回签合同记录主键"),
        Column(
            "purchase_order_id",
            ID,
            nullable=False,
            comment="子采购单本地主键，指向 source_purchase_orders.id",
        ),
        Column("customs_declaration_id", ID, nullable=False, comment="所属报关单本地主键，决定归档文件夹"),
        Column("order_no", String(150), nullable=False, comment="子采购单号"),
        Column("original_filename", String(255), nullable=False, comment="上传时的原文件名"),
        Column("filename", String(255), nullable=False, comment="归档文件名：回签合同_子采购单号"),
        Column("sha256", CHAR(64), nullable=False, comment="文件内容摘要，用于防止静默覆盖"),
        Column("archive_path", String(2048), nullable=False, comment="共享盘路径；文件正文不存数据库"),
        Column("uploaded_by", String(200), nullable=False, comment="上传的认证身份"),
        *timestamps(),
        UniqueConstraint("purchase_order_id", name="uq_task_signed_contract_order"),
        comment="回签合同上传记录，按子采购单一份，不保存文件正文",
        **table_options,
    )
    with op.batch_alter_table("task_tasks") as batch:
        batch.drop_constraint("ck_task_status", type_="check")
        batch.alter_column(
            "status",
            existing_type=String(24),
            existing_nullable=False,
            existing_server_default="documents_pending",
            existing_comment=OLD_COMMENT,
            comment=NEW_COMMENT,
        )
        batch.create_check_constraint("ck_task_status", f"status IN {NEW_STATUSES}")


def downgrade():
    raise RuntimeError("资料归档记录与新任务状态可能已被使用，不能降级删除；请保留数据")
