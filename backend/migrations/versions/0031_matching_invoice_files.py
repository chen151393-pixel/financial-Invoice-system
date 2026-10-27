"""matching：发票文件归档记录（2026-10-26）。

比对通过的发票 PDF/图片人工批量上传，按发票号码找到分配的子采购单，存入所属报关单文件夹；
数据库只记录路径与校验值，不保存文件正文。只归档，不改变比对、收票与任务状态。
"""

from alembic import op
from backend.core.schema import ID, table_options, timestamps
from sqlalchemy import CHAR, Column, String, UniqueConstraint

revision = "0031_matching_invoice_files"
down_revision = "0030_task_signed_upload_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "matching_invoice_files",
        Column("id", ID, primary_key=True, autoincrement=True, comment="发票文件记录主键"),
        Column("invoice_id", ID, nullable=False, comment="本地发票 ID，指向 invoice_headers.id"),
        Column(
            "customs_declaration_id",
            ID,
            nullable=False,
            comment="归档所在报关单本地主键，指向 source_customs_declarations.id；发票跨报关单时各存一份",
        ),
        Column("invoice_no", String(100), nullable=False, comment="发票号码"),
        Column("original_filename", String(255), nullable=False, comment="上传时的原文件名"),
        Column("filename", String(255), nullable=False, comment="归档文件名：发票_发票号码"),
        Column("sha256", CHAR(64), nullable=False, comment="文件内容摘要，用于防止静默覆盖"),
        Column("archive_path", String(2048), nullable=False, comment="共享盘路径；文件正文不存数据库"),
        Column("uploaded_by", String(200), nullable=False, comment="上传的认证身份"),
        *timestamps(),
        UniqueConstraint("invoice_id", "customs_declaration_id", name="uq_matching_invoice_file"),
        comment="发票文件归档记录，按发票×报关单一份，不保存文件正文",
        **table_options,
    )


def downgrade():
    raise RuntimeError("发票文件归档记录可能已被使用，不能降级删除；请保留数据")
