"""审核冻结的子采购行范围，不可修改。"""

from sqlalchemy import CHAR, Column, ForeignKey, Index, Numeric, String, Table, UniqueConstraint

from backend.core.schema import ID, schema_metadata, table_options, timestamps

lines = Table(
    "review_lines",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("review_id", ID, ForeignKey("review_records.id", name="fk_review_line_record"), nullable=False),
    Column("purchase_order_id", ID, nullable=False, comment="source_purchase_orders.id"),
    Column("purchase_line_id", ID, nullable=False, comment="source_purchase_order_lines.id"),
    Column("customs_line_id", ID, comment="source_customs_lines.id"),
    Column("supplier_id", ID, comment="任务分组用"),
    Column("company_id", ID, comment="任务分组用"),
    Column("order_no", String(150), nullable=False),
    Column("item_name", String(500)),
    Column("specification", String(500)),
    Column("currency", String(20)),
    Column("quantity", Numeric(26, 8), comment="冻结的采购口径数量"),
    Column("unit", String(50)),
    Column("amount", Numeric(24, 6), comment="冻结的含税金额"),
    Column("line_sha256", CHAR(64), nullable=False, comment="冻结时子采购行内容摘要"),
    *timestamps(),
    UniqueConstraint("review_id", "purchase_line_id", name="uq_review_line"),
    Index("ix_review_line_purchase", "purchase_line_id"),
    comment="审核冻结的子采购行范围，不可修改",
    **table_options,
)
