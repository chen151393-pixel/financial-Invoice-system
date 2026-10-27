"""查询快照关联的供应商，只用于财务列表筛选。"""

from sqlalchemy import Column, ForeignKey, Index, String, Table, UniqueConstraint

from backend.core.schema import ID, schema_metadata, table_options, timestamps

snapshot_suppliers = Table(
    "review_snapshot_suppliers",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="财务快照供应商关联主键"),
    Column(
        "declaration_id",
        ID,
        ForeignKey("review_declaration_snapshots.customs_declaration_id", name="fk_review_supplier_snapshot"),
        nullable=False,
        comment="财务快照对应的来源报关单 ID",
    ),
    Column("supplier_id", ID, nullable=False, comment="来源供应商 ID；跨模块不建外键"),
    Column("ns_account", String(100), nullable=False, comment="来源 NS 账套"),
    Column("name", String(500), nullable=False, comment="来源供应商名称快照"),
    *timestamps(),
    UniqueConstraint("declaration_id", "supplier_id", name="uq_review_snapshot_supplier"),
    Index("ix_review_snapshot_supplier", "supplier_id", "declaration_id"),
    comment="财务查询快照的供应商筛选投影",
    **table_options,
)
