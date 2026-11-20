"""结汇批次的提单：银行资料包必备件，并为销售合同提供装运口岸、目的口岸与装船日期。

文件本体保存在结汇资料目录（SETTLEMENT_DOCUMENT_ROOT），数据库只记录文件标识、校验值与解析 / 人工确认的字段。
移除为软删除：removed_at 非空的提单不参与资料核对与打包。
"""

from sqlalchemy import CHAR, JSON, CheckConstraint, Column, Date, ForeignKey, Index, Integer, String, Table

from backend.core.schema import ID, TIMESTAMP, identifier, schema_metadata, table_options, timestamps

from .document_group import settlement_document_groups

settlement_bills = Table(
    "settlement_bills",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="提单本地主键"),
    Column(
        "batch_id",
        ID,
        ForeignKey("settlement_batches.id", name="fk_settlement_bill_batch"),
        nullable=True,
        comment="所属结汇批次，指向 settlement_batches.id",
    ),
    Column(
        "document_group_id", ID, ForeignKey(settlement_document_groups.c.id), comment="所属直接收汇资料组"
    ),
    Column("direct_declaration_no", identifier(150), comment="直接收汇资料所属报关单；与批次二选一"),
    Column("file_id", identifier(36), nullable=False, comment="资料目录中的文件标识（服务端生成的 UUID）"),
    Column("file_name", String(255), nullable=False, comment="上传时的原文件名，仅展示"),
    Column("sha256", CHAR(64), nullable=False, comment="文件内容 SHA-256，用于识别同一批次内重复上传"),
    Column("size_bytes", Integer, nullable=False, comment="文件大小，字节"),
    Column("bl_no", String(100), comment="提单号；解析得到或人工填写"),
    Column("port_of_loading", String(200), comment="装运口岸（英文，取自提单）"),
    Column("port_of_discharge", String(200), comment="目的口岸（英文，取自提单）"),
    Column("on_board_date", Date, comment="装船日期"),
    Column("declaration_nos", JSON, nullable=False, comment="该提单对应的报关单号列表（须属于本批次）"),
    Column("parse_note", String(500), comment="自动解析说明，如未能读取文字需人工填写"),
    Column("uploaded_by", String(190), nullable=False, comment="上传人（认证身份）"),
    Column("uploaded_at", TIMESTAMP, nullable=False, comment="上传时间，UTC"),
    Column("confirmed_by", String(190), comment="最近一次人工修改字段的操作人"),
    Column("removed_by", String(190), comment="移除人；未移除为空"),
    Column("removed_at", TIMESTAMP, comment="移除时间，UTC；非空表示已移除"),
    *timestamps(),
    Index("ix_settlement_bill_batch", "batch_id", "removed_at"),
    CheckConstraint(
        "(CASE WHEN batch_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN direct_declaration_no IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN document_group_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
        name="ck_settlement_bill_source",
    ),
    Index("ix_settlement_bill_group", "document_group_id", "removed_at"),
    Index("ix_settlement_bill_direct", "direct_declaration_no", "removed_at"),
    comment="结汇批次的提单文件及装运口岸、目的口岸、装船日期",
    **table_options,
)
