"""发票文件：比对通过的发票 PDF/图片人工上传后，按报关单各存一份到共享盘，只记录路径与校验值。"""

from sqlalchemy import CHAR, Column, String, Table, UniqueConstraint

from backend.core.schema import ID, schema_metadata, table_options, timestamps

invoice_files = Table(
    "matching_invoice_files",
    schema_metadata,
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
