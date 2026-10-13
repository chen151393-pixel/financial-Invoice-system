"""任务行：每条子采购行的应开与已收。"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    ForeignKey,
    Index,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    text,
)

from backend.core.schema import ID, schema_metadata, table_options, timestamps

task_lines = Table(
    "task_lines",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("task_id", ID, ForeignKey("task_tasks.id", name="fk_task_line_task"), nullable=False),
    Column("review_line_id", ID, nullable=False, comment="review_lines.id，应开值来源"),
    Column("purchase_order_id", ID, nullable=False),
    Column("purchase_line_id", ID, nullable=False, comment="开票单元"),
    Column("expected_quantity", Numeric(26, 8)),
    Column("unit", String(50)),
    Column("expected_amount", Numeric(24, 6), comment="来源金额缺失时为空，只能人工按差异结束"),
    Column(
        "received_quantity",
        Numeric(26, 8),
        nullable=False,
        server_default=text("0"),
        comment="已通过分配合计（缓存）",
    ),
    Column("received_amount", Numeric(24, 6), nullable=False, server_default=text("0")),
    Column("status", String(24), nullable=False, server_default="open"),
    Column("over_invoiced", Boolean, nullable=False, server_default=text("0")),
    Column("closed_with_difference", Boolean, nullable=False, server_default=text("0")),
    Column(
        "active_purchase_line_id",
        ID,
        Computed("CASE WHEN status <> 'superseded' THEN purchase_line_id END", persisted=True),
        comment="同一子采购行只有一条有效任务行",
    ),
    *timestamps(),
    UniqueConstraint("active_purchase_line_id", name="uq_task_line_active"),
    UniqueConstraint("task_id", "purchase_line_id", name="uq_task_line_task"),
    Index("ix_task_line_purchase", "purchase_line_id"),
    CheckConstraint("status IN ('open','partial','received','superseded')", name="ck_task_line_status"),
    comment="任务行：每条子采购行的应开与已收",
    **table_options,
)
