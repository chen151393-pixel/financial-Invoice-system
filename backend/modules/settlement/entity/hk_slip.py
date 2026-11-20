"""香港到账银行水单：一批次一份原件，与回款同事务登记。"""

from sqlalchemy import Column, ForeignKey, String, Table

from backend.core.schema import ID, identifier, schema_metadata, table_options, timestamps

settlement_hk_slips = Table(
    "settlement_hk_slips",
    schema_metadata,
    Column(
        "batch_id",
        ID,
        ForeignKey("settlement_batches.id"),
        primary_key=True,
        autoincrement=False,
        comment="所属香港批次主键，一批次一份水单",
    ),
    Column("file_name", String(255), nullable=False, comment="银行水单原始文件名"),
    Column("file_id", identifier(36), nullable=False, comment="资料目录内服务端生成的 PDF 文件标识"),
    Column("sha256", identifier(64), nullable=False, comment="原件 SHA-256 校验值"),
    Column("uploaded_by", String(190), nullable=False, comment="登记操作人，来自认证身份"),
    *timestamps(),
    comment="香港到账银行水单原件，随批次留存不写 NS",
    **table_options,
)
