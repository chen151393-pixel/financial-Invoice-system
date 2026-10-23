"""回签合同：供应商签回的子采购合同，人工批量上传，按子采购单各一份。"""

from sqlalchemy import CHAR, Column, String, Table, UniqueConstraint

from backend.core.schema import ID, schema_metadata, table_options, timestamps

signed_contracts = Table(
    "task_signed_contracts",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="回签合同记录主键"),
    Column(
        "purchase_order_id", ID, nullable=False, comment="子采购单本地主键，指向 source_purchase_orders.id"
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
