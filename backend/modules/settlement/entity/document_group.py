"""直接收汇资料组及成员；只组织业务资料，不登记或分配收款。"""

from sqlalchemy import JSON, Column, ForeignKey, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, identifier, schema_metadata, table_options, timestamps

settlement_document_groups = Table(
    "settlement_document_groups",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="本地自增主键"),
    Column("group_no", identifier(40), nullable=False, unique=True, comment="资料组编号"),
    Column("request_id", identifier(36), nullable=False, unique=True, comment="创建幂等请求标识"),
    Column("consignee", String(200), nullable=False, comment="创建时境外收货人"),
    Column("currency", String(10), nullable=False, comment="创建时币种，不跨币种合并"),
    Column("created_by", String(190), nullable=False, comment="创建人，取认证身份"),
    Column("initial_declaration_nos", JSON, comment="创建时成员快照，合并后仍保留原始范围"),
    Column(
        "merged_into_id",
        ID,
        ForeignKey("settlement_document_groups.id", name="fk_settlement_document_group_successor"),
        comment="合并后的新资料组，原组保留供追溯",
    ),
    Column("merged_at", TIMESTAMP, comment="合并时间，UTC"),
    Column("merged_by", String(190), comment="合并操作人，取认证身份"),
    Column("basis_history", JSON, comment="人工确认更新来源的前后依据、时间和认证操作者"),
    *timestamps(),
    comment="直接收汇资料组，同收货人同币种，可含不同申报抬头",
    **table_options,
)
settlement_document_group_items = Table(
    "settlement_document_group_items",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="本地自增主键"),
    Column(
        "group_id",
        ID,
        ForeignKey(settlement_document_groups.c.id),
        nullable=False,
        comment="所属直接收汇资料组",
    ),
    Column("declaration_no", identifier(150), nullable=False, comment="资料组内报关单，一票只能属于一组"),
    Column("created_at", TIMESTAMP, nullable=False, comment="成员归组时间，UTC"),
    UniqueConstraint("declaration_no", name="uq_settlement_document_group_declaration"),
    comment="直接收汇资料组成员，一张报关单只属于一组",
    **table_options,
)
