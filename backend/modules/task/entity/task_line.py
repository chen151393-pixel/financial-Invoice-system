"""任务行：每条子采购行的应开与已收。"""

from sqlalchemy import (
    CHAR,
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
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "task_id",
        ID,
        ForeignKey("task_tasks.id", name="fk_task_line_task"),
        comment="开票任务 ID，指向 task_tasks.id",
        nullable=False,
    ),
    Column(
        "review_line_id", ID, nullable=False, comment="审核冻结行 ID，逻辑指向 review_lines.id；应开值的来源"
    ),
    Column(
        "purchase_order_id", ID, comment="子采购单本地主键，指向 source_purchase_orders.id", nullable=False
    ),
    Column(
        "purchase_line_id",
        ID,
        nullable=False,
        comment="子采购明细 ID，指向 source_purchase_order_lines.id；开票业务围绕此身份组织",
    ),
    Column("expected_quantity", Numeric(26, 8), comment="审核冻结的应开采购数量"),
    Column("unit", String(50), comment="该表所属业务口径的单位，与本行 quantity 配套"),
    Column("expected_amount", Numeric(24, 6), comment="审核冻结的应开含税金额；来源缺失为 NULL，不能当作 0"),
    Column(
        "received_quantity",
        Numeric(26, 8),
        nullable=False,
        server_default=text("0"),
        comment="有效分配按采购口径汇总的已收数量缓存，可由台账重算",
    ),
    Column(
        "received_amount",
        Numeric(24, 6),
        comment="有效分配汇总的已收含税金额缓存，可由台账重算",
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "status",
        String(24),
        comment="任务行状态：open 未收；partial 部分收票；received 已收齐或差异结束；superseded 已替代",
        nullable=False,
        server_default="open",
    ),
    Column(
        "over_invoiced",
        Boolean,
        comment="是否超过应开数量或金额；超开标记不等于任务完成",
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "closed_with_difference",
        Boolean,
        comment="当前是否依据人工差异结束决定结案；台账变化后会重算",
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "active_purchase_line_id",
        ID,
        Computed("CASE WHEN status <> 'superseded' THEN purchase_line_id END", persisted=True),
        comment="自动生成：未被 superseded 的任务行取子采购行 ID；已收齐行仍占唯一位置",
    ),
    Column("purchase_basis_id", ID, comment="全局子采购行开票依据版本 ID，逻辑指向 review_purchase_bases.id"),
    Column("ledger_sha256", CHAR(64), comment="分配台账摘要，绑定当前差异结束决定并检测台账变化"),
    Column(
        "requires_review",
        Boolean,
        comment="是否存在待复核占用或依据问题；此时不能显示为完成",
        nullable=False,
        server_default="0",
    ),
    Column("closure_event_id", ID, comment="当前有效差异结束事件 ID，逻辑指向 task_events.id"),
    Column(
        "pending_quantity",
        Numeric(26, 8),
        comment="已确认但不能计入有效收票的待复核采购数量；不是剩余应开数量",
        nullable=False,
        server_default="0",
    ),
    Column(
        "pending_amount",
        Numeric(24, 6),
        comment="已确认但不能计入有效收票的待复核含税金额；不是剩余应开金额",
        nullable=False,
        server_default="0",
    ),
    *timestamps(),
    UniqueConstraint("active_purchase_line_id", name="uq_task_line_active"),
    UniqueConstraint("task_id", "purchase_line_id", name="uq_task_line_task"),
    Index("ix_task_line_purchase", "purchase_line_id"),
    CheckConstraint("status IN ('open','partial','received','superseded')", name="ck_task_line_status"),
    comment="任务行：每条子采购行的应开与已收",
    **table_options,
)
