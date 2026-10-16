"""报关单与子采购单的关联，支持多对多与行级。"""

from sqlalchemy import CheckConstraint, Column, Computed, ForeignKey, Index, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

customs_purchase_links = Table(
    "source_customs_purchase_links",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "customs_declaration_id",
        ID,
        ForeignKey("source_customs_declarations.id", name="fk_source_link_customs"),
        comment="报关单本地主键，指向 source_customs_declarations.id",
        nullable=False,
    ),
    Column(
        "purchase_order_id",
        ID,
        ForeignKey("source_purchase_orders.id", name="fk_source_link_purchase"),
        comment="子采购单本地主键，指向 source_purchase_orders.id",
        nullable=False,
    ),
    Column(
        "customs_line_id",
        ID,
        ForeignKey("source_customs_lines.id", name="fk_source_link_customs_line"),
        comment="报关明细 ID，指向 source_customs_lines.id；未定位到行时可为空",
    ),
    Column(
        "purchase_line_id",
        ID,
        ForeignKey("source_purchase_order_lines.id", name="fk_source_link_purchase_line"),
        comment="子采购明细 ID，指向 source_purchase_order_lines.id；开票业务围绕此身份组织",
    ),
    Column(
        "evidence",
        String(24),
        nullable=False,
        comment="关联证据类别：ns_reference NS 引用；ns_v3 整单关联；local_packing 本地 Packing 定位",
    ),
    Column(
        "status",
        String(24),
        comment="关联状态：active 有效；stale 已过期",
        nullable=False,
        server_default="active",
    ),
    # 唯一约束中可空列用 0 代替，避免多个空值绕过唯一性。
    Column(
        "customs_line_key",
        ID,
        Computed("COALESCE(customs_line_id, 0)", persisted=True),
        comment="自动生成：customs_line_id 为空时取 0，避免空值绕过关联唯一约束",
    ),
    Column(
        "purchase_line_key",
        ID,
        Computed("COALESCE(purchase_line_id, 0)", persisted=True),
        comment="自动生成：purchase_line_id 为空时取 0，避免空值绕过关联唯一约束",
    ),
    Column("synced_at", TIMESTAMP, comment="本次成功保存来源数据的时间，UTC", nullable=False),
    *timestamps(),
    UniqueConstraint(
        "customs_declaration_id",
        "purchase_order_id",
        "customs_line_key",
        "purchase_line_key",
        name="uq_source_link",
    ),
    Index("ix_source_link_purchase", "purchase_order_id", "status"),
    Index("ix_source_link_purchase_line", "purchase_line_id"),
    CheckConstraint("evidence IN ('ns_reference','ns_v3','local_packing')", name="ck_source_link_evidence"),
    CheckConstraint("status IN ('active','stale')", name="ck_source_link_status"),
    comment="报关单与子采购单的关联，支持多对多与行级",
    **table_options,
)
