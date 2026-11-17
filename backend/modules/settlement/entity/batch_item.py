"""结汇批次明细：批次包含的报关单及建批次时冻结的报关金额。

同一报关单只能在一个有效批次中：active_declaration_no 在有效时等于报关单号、作废后置空，借唯一约束防止重复结汇。
"""

from sqlalchemy import Column, Date, ForeignKey, Index, Integer, Numeric, String, Table, UniqueConstraint

from backend.core.schema import ID, identifier, schema_metadata, table_options, timestamps

settlement_batch_items = Table(
    "settlement_batch_items",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="批次明细本地主键"),
    Column(
        "batch_id",
        ID,
        ForeignKey("settlement_batches.id", name="fk_settlement_item_batch"),
        nullable=False,
        comment="所属批次，指向 settlement_batches.id",
    ),
    Column("declaration_no", identifier(150), nullable=False, comment="真实报关单号（海关出口报关单号）"),
    Column(
        "active_declaration_no",
        identifier(150),
        comment="有效占用：批次有效时等于报关单号，作废后为空；唯一约束防止同一报关单重复结汇",
    ),
    Column("record_no", String(150), comment="NS 报关记录 CD 编号（建批次时读取，仅展示）"),
    Column("receipt_id", ID, comment="海关回执本地 ID（review_customs_receipts.id，跨模块不建外键）"),
    Column("receipt_revision", Integer, comment="建批次时海关回执版本"),
    Column("sales_orders", String(500), comment="出口合同号 / 销售订单号，多个以顿号分隔"),
    Column("consignee", String(500), nullable=False, comment="境外收货人（海关回执）"),
    Column("export_date", Date, comment="出口日期（海关回执）"),
    Column("currency", String(20), nullable=False, comment="成交币制"),
    Column("declared_amount", Numeric(24, 6), nullable=False, comment="建批次时冻结的成交总价合计"),
    *timestamps(),
    UniqueConstraint("batch_id", "declaration_no", name="uq_settlement_item_batch_declaration"),
    UniqueConstraint("active_declaration_no", name="uq_settlement_item_active_declaration"),
    Index("ix_settlement_item_declaration", "declaration_no"),
    comment="结汇批次包含的报关单，金额按建批次时的海关回执冻结",
    **table_options,
)
