"""新表结构基线：一次创建 docs/architecture/database.md 第 4 节的 24 张表。

与设计文档的差异（为同时支持 MySQL 与 SQLite 测试库）：
- 生成列用标准 CASE / COALESCE，不用 MySQL 专有的 IF() / IFNULL() / CONCAT()；
- updated_at 由 DAO 在更新时写入，不使用 MySQL 专有的 ON UPDATE；
- 发票行表名为 invoice_items，避免与过渡期仍在使用的旧表 invoice_lines 同名。

只创建新表，不读写旧表。
"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP, table_options, utc_now

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

AMOUNT = sa.Numeric(24, 6)
QUANTITY = sa.Numeric(26, 8)
PRICE = sa.Numeric(24, 8)
INVOICE_AMOUNT = sa.Numeric(18, 2)
SHA256 = sa.CHAR(64)

# 创建顺序即依赖顺序；downgrade 逆序删除。
TABLES = [
    "source_suppliers",
    "source_companies",
    "source_raw_records",
    "source_parent_orders",
    "source_parent_order_lines",
    "source_purchase_orders",
    "source_purchase_order_lines",
    "source_customs_declarations",
    "source_customs_lines",
    "source_customs_purchase_links",
    "review_records",
    "review_lines",
    "task_supplier_groups",
    "task_tasks",
    "task_lines",
    "task_documents",
    "task_notifications",
    "task_events",
    "invoice_raw_records",
    "invoice_headers",
    "invoice_items",
    "matching_allocations",
    "sync_runs",
    "sync_cursors",
]


def pk():
    return sa.Column("id", ID, primary_key=True, autoincrement=True)


def ref(name, nullable=False, comment=None):
    return sa.Column(name, ID, nullable=nullable, comment=comment)


def stamps():
    return [
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=utc_now()),
        sa.Column(
            "updated_at",
            TIMESTAMP,
            nullable=False,
            server_default=utc_now(),
            comment="由 DAO 在每次更新时写入",
        ),
    ]


def active_flag():
    return sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1"))


def generated(name, expression, comment):
    return sa.Column(name, ID, sa.Computed(expression, persisted=True), comment=comment)


def check_in(name, column, values):
    allowed = ",".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({allowed})", name=name)


def create(name, comment, *items):
    op.create_table(name, *items, comment=comment, **table_options)


def create_source():
    create(
        "source_suppliers",
        "供应商（NS vendor）",
        pk(),
        sa.Column("ns_account", sa.String(100), nullable=False),
        sa.Column("ns_internal_id", sa.String(190), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_normalized", sa.String(255), nullable=False, comment="名称比对用"),
        active_flag(),
        *stamps(),
        sa.UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_supplier_ns"),
        sa.Index("ix_source_supplier_name", "ns_account", "name_normalized"),
    )
    create(
        "source_companies",
        "采购公司（NS 子公司），与发票购买方比对",
        pk(),
        sa.Column("ns_account", sa.String(100), nullable=False),
        sa.Column("ns_internal_id", sa.String(190), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_normalized", sa.String(255), nullable=False),
        active_flag(),
        *stamps(),
        sa.UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_company_ns"),
    )
    create(
        "source_raw_records",
        "NS 原始数据；内容变化时追加一行，主表指向最新一行",
        pk(),
        sa.Column("ns_account", sa.String(100), nullable=False),
        sa.Column(
            "record_type", sa.String(100), nullable=False, comment="NS 记录类型；关联依据为 relation_evidence"
        ),
        sa.Column("ns_internal_id", sa.String(190), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", SHA256, nullable=False),
        sa.Column("fetched_at", TIMESTAMP, nullable=False),
        *stamps(),
        sa.UniqueConstraint(
            "ns_account", "record_type", "ns_internal_id", "payload_sha256", name="uq_source_raw_content"
        ),
    )
    create(
        "source_parent_orders",
        "母采购单",
        pk(),
        sa.Column("ns_account", sa.String(100), nullable=False),
        sa.Column("ns_internal_id", sa.String(190), nullable=False),
        sa.Column("ns_record_type", sa.String(100), nullable=False),
        sa.Column("order_no", sa.String(150)),
        sa.Column("order_date", sa.Date()),
        ref("supplier_id", nullable=True),
        ref("company_id", nullable=True),
        sa.Column("currency", sa.String(20)),
        sa.Column("total_amount", AMOUNT),
        sa.Column("source_status", sa.String(100), comment="NS 原始业务状态"),
        sa.Column("source_modified_at", TIMESTAMP),
        sa.Column("synced_at", TIMESTAMP, nullable=False),
        active_flag(),
        ref("raw_record_id", nullable=True),
        *stamps(),
        sa.UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_parent_ns"),
        sa.Index("ix_source_parent_no", "ns_account", "order_no"),
        sa.ForeignKeyConstraint(["supplier_id"], ["source_suppliers.id"], name="fk_source_parent_supplier"),
        sa.ForeignKeyConstraint(["company_id"], ["source_companies.id"], name="fk_source_parent_company"),
        sa.ForeignKeyConstraint(["raw_record_id"], ["source_raw_records.id"], name="fk_source_parent_raw"),
    )
    create(
        "source_parent_order_lines",
        "母采购行",
        pk(),
        ref("parent_order_id"),
        sa.Column(
            "source_line_key", sa.String(190), nullable=False, comment="稳定行键 transactionline:<uniquekey>"
        ),
        sa.Column("line_no", sa.String(40)),
        sa.Column("item_code", sa.String(150)),
        sa.Column("item_name", sa.String(500)),
        sa.Column("declaration_name", sa.String(500)),
        sa.Column("specification", sa.String(500)),
        sa.Column("quantity", QUANTITY),
        sa.Column("unit", sa.String(50)),
        sa.Column("unit_price", PRICE),
        sa.Column("amount", AMOUNT),
        active_flag(),
        *stamps(),
        sa.UniqueConstraint("parent_order_id", "source_line_key", name="uq_source_parent_line"),
        sa.ForeignKeyConstraint(
            ["parent_order_id"], ["source_parent_orders.id"], name="fk_source_parent_line_order"
        ),
    )
    create(
        "source_purchase_orders",
        "子采购单",
        pk(),
        sa.Column("ns_account", sa.String(100), nullable=False),
        sa.Column("ns_internal_id", sa.String(190), nullable=False),
        sa.Column("order_no", sa.String(150), nullable=False, comment="子采购单号"),
        sa.Column("order_date", sa.Date()),
        sa.Column("pl_no", sa.String(100)),
        ref("parent_order_id", nullable=True),
        sa.Column("parent_relation_status", sa.String(24), nullable=False, server_default="unknown"),
        ref("supplier_id", nullable=True),
        ref("company_id", nullable=True),
        sa.Column("currency", sa.String(20)),
        sa.Column("total_amount", AMOUNT),
        sa.Column(
            "detail_status",
            sa.String(24),
            nullable=False,
            server_default="pending",
            comment="明细是否完整读取",
        ),
        sa.Column("source_modified_at", TIMESTAMP),
        sa.Column("synced_at", TIMESTAMP, nullable=False),
        active_flag(),
        ref("raw_record_id", nullable=True),
        *stamps(),
        sa.UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_purchase_ns"),
        sa.Index("ix_source_purchase_no", "ns_account", "order_no"),
        sa.Index("ix_source_purchase_pl", "ns_account", "pl_no"),
        sa.Index("ix_source_purchase_supplier", "supplier_id"),
        sa.ForeignKeyConstraint(
            ["parent_order_id"], ["source_parent_orders.id"], name="fk_source_purchase_parent"
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["source_suppliers.id"], name="fk_source_purchase_supplier"),
        sa.ForeignKeyConstraint(["company_id"], ["source_companies.id"], name="fk_source_purchase_company"),
        sa.ForeignKeyConstraint(["raw_record_id"], ["source_raw_records.id"], name="fk_source_purchase_raw"),
        check_in(
            "ck_source_purchase_parent_status", "parent_relation_status", ["unknown", "no_parent", "linked"]
        ),
        check_in("ck_source_purchase_detail_status", "detail_status", ["pending", "complete", "failed"]),
    )
    create(
        "source_purchase_order_lines",
        "子采购行：开票单元",
        pk(),
        ref("purchase_order_id"),
        sa.Column("source_line_key", sa.String(190), nullable=False),
        sa.Column("line_no", sa.String(40)),
        sa.Column("item_code", sa.String(150)),
        sa.Column("item_name", sa.String(500)),
        sa.Column("item_name_normalized", sa.String(500), comment="品名比对用"),
        sa.Column("declaration_name", sa.String(500), comment="报关品名"),
        sa.Column("specification", sa.String(500)),
        sa.Column("quantity", QUANTITY, comment="采购数量（开票口径）"),
        sa.Column(
            "unit",
            sa.String(50),
            comment="采购单位（开票口径），NS custrecord_swc_subpo_item_unit；未返回时为空",
        ),
        sa.Column("declared_quantity", QUANTITY, comment="报关数量，只用于报关核对"),
        sa.Column("declared_unit", sa.String(50)),
        sa.Column("unit_price", PRICE, comment="含税单价"),
        sa.Column("amount", AMOUNT, comment="含税金额；来源缺失时为空"),
        sa.Column("amount_status", sa.String(24), nullable=False, server_default="matched"),
        ref("parent_line_id", nullable=True),
        active_flag(),
        *stamps(),
        sa.UniqueConstraint("purchase_order_id", "source_line_key", name="uq_source_purchase_line"),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["source_purchase_orders.id"], name="fk_source_purchase_line_order"
        ),
        sa.ForeignKeyConstraint(
            ["parent_line_id"], ["source_parent_order_lines.id"], name="fk_source_purchase_line_parent"
        ),
        check_in("ck_source_purchase_line_amount", "amount_status", ["matched", "source_missing"]),
    )
    create(
        "source_customs_declarations",
        "报关单",
        pk(),
        sa.Column("ns_account", sa.String(100), nullable=False),
        sa.Column("ns_internal_id", sa.String(190), nullable=False),
        sa.Column("record_no", sa.String(150), comment="CD 编号"),
        sa.Column("declaration_no", sa.String(150), comment="真实报关单号"),
        sa.Column("declaration_date", sa.Date()),
        ref("declarant_company_id", nullable=True),
        sa.Column("detail_status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column(
            "relation_status",
            sa.String(24),
            nullable=False,
            server_default="partial",
            comment="关联依据完整性：partial / complete；不是审核结论",
        ),
        sa.Column("relation_issues", sa.JSON(), comment="关联依据不完整的原因列表"),
        sa.Column("content_sha256", SHA256, comment="报关单 + 关联子采购的展示内容摘要，审核比对用"),
        sa.Column("source_modified_at", TIMESTAMP),
        sa.Column("synced_at", TIMESTAMP, nullable=False),
        active_flag(),
        ref("raw_record_id", nullable=True),
        *stamps(),
        sa.UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_customs_ns"),
        sa.Index("ix_source_customs_record", "ns_account", "record_no"),
        sa.Index("ix_source_customs_number", "ns_account", "declaration_no"),
        sa.ForeignKeyConstraint(
            ["declarant_company_id"], ["source_companies.id"], name="fk_source_customs_company"
        ),
        sa.ForeignKeyConstraint(["raw_record_id"], ["source_raw_records.id"], name="fk_source_customs_raw"),
        check_in("ck_source_customs_detail_status", "detail_status", ["pending", "complete", "failed"]),
        check_in("ck_source_customs_relation_status", "relation_status", ["partial", "complete"]),
    )
    create(
        "source_customs_lines",
        "报关明细",
        pk(),
        ref("customs_declaration_id"),
        sa.Column("source_line_key", sa.String(190), nullable=False),
        sa.Column("line_no", sa.String(40)),
        sa.Column("pl_no", sa.String(100)),
        sa.Column("sales_order_no", sa.String(150)),
        ref("company_id", nullable=True),
        sa.Column("origin_place", sa.String(255)),
        sa.Column("item_code", sa.String(150)),
        sa.Column("declaration_name", sa.String(500)),
        sa.Column("specification", sa.String(500)),
        sa.Column("quantity", QUANTITY),
        sa.Column("unit", sa.String(50)),
        sa.Column("declared_quantity", QUANTITY),
        sa.Column("declared_unit", sa.String(50)),
        sa.Column("unit_price", PRICE),
        sa.Column("amount", AMOUNT),
        sa.Column("currency", sa.String(20)),
        active_flag(),
        *stamps(),
        sa.UniqueConstraint("customs_declaration_id", "source_line_key", name="uq_source_customs_line"),
        sa.Index("ix_source_customs_line_pl", "pl_no"),
        sa.ForeignKeyConstraint(
            ["customs_declaration_id"], ["source_customs_declarations.id"], name="fk_source_customs_line_head"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["source_companies.id"], name="fk_source_customs_line_company"
        ),
    )
    create(
        "source_customs_purchase_links",
        "报关单与子采购单的关联，支持多对多与行级",
        pk(),
        ref("customs_declaration_id"),
        ref("purchase_order_id"),
        ref("customs_line_id", nullable=True, comment="行级关系；只有单头级关系时为空"),
        ref("purchase_line_id", nullable=True),
        sa.Column("evidence", sa.String(24), nullable=False, comment="ns_reference / ns_v3 / local_packing"),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        # 唯一约束中可空列用 0 代替，避免多个空值绕过唯一性。
        generated("customs_line_key", "COALESCE(customs_line_id, 0)", "唯一约束用"),
        generated("purchase_line_key", "COALESCE(purchase_line_id, 0)", "唯一约束用"),
        sa.Column("synced_at", TIMESTAMP, nullable=False),
        *stamps(),
        sa.UniqueConstraint(
            "customs_declaration_id",
            "purchase_order_id",
            "customs_line_key",
            "purchase_line_key",
            name="uq_source_link",
        ),
        sa.Index("ix_source_link_purchase", "purchase_order_id", "status"),
        sa.Index("ix_source_link_purchase_line", "purchase_line_id"),
        sa.ForeignKeyConstraint(
            ["customs_declaration_id"], ["source_customs_declarations.id"], name="fk_source_link_customs"
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["source_purchase_orders.id"], name="fk_source_link_purchase"
        ),
        sa.ForeignKeyConstraint(
            ["customs_line_id"], ["source_customs_lines.id"], name="fk_source_link_customs_line"
        ),
        sa.ForeignKeyConstraint(
            ["purchase_line_id"], ["source_purchase_order_lines.id"], name="fk_source_link_purchase_line"
        ),
        check_in("ck_source_link_evidence", "evidence", ["ns_reference", "ns_v3", "local_packing"]),
        check_in("ck_source_link_status", "status", ["active", "stale"]),
    )


def create_review():
    create(
        "review_records",
        "审核记录：一次审核通过一行，不可修改，全部行即审核历史",
        pk(),
        sa.Column("ns_account", sa.String(100), nullable=False),
        ref("customs_declaration_id", comment="source_customs_declarations.id"),
        sa.Column("record_no", sa.String(150), comment="冗余，CD 编号"),
        sa.Column("revision", sa.Integer(), nullable=False, comment="同一报关单第几次审核"),
        sa.Column("content_sha256", SHA256, nullable=False, comment="审核时看到的内容摘要"),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("approved_by", sa.String(200), nullable=False),
        sa.Column("approved_at", TIMESTAMP, nullable=False),
        sa.Column("note", sa.String(300)),
        generated(
            "active_declaration_id",
            "CASE WHEN status = 'active' THEN customs_declaration_id END",
            "一张报关单只有一条有效审核",
        ),
        *stamps(),
        sa.UniqueConstraint("customs_declaration_id", "revision", name="uq_review_revision"),
        sa.UniqueConstraint("active_declaration_id", name="uq_review_active"),
        check_in("ck_review_status", "status", ["active", "superseded"]),
    )
    create(
        "review_lines",
        "审核冻结的子采购行范围，不可修改",
        pk(),
        ref("review_id"),
        ref("purchase_order_id", comment="source_purchase_orders.id"),
        ref("purchase_line_id", comment="source_purchase_order_lines.id"),
        ref("customs_line_id", nullable=True, comment="source_customs_lines.id"),
        ref("supplier_id", nullable=True, comment="任务分组用"),
        ref("company_id", nullable=True, comment="任务分组用"),
        sa.Column("order_no", sa.String(150), nullable=False),
        sa.Column("item_name", sa.String(500)),
        sa.Column("specification", sa.String(500)),
        sa.Column("currency", sa.String(20)),
        sa.Column("quantity", QUANTITY, comment="冻结的采购口径数量"),
        sa.Column("unit", sa.String(50)),
        sa.Column("amount", AMOUNT, comment="冻结的含税金额"),
        sa.Column("line_sha256", SHA256, nullable=False, comment="冻结时子采购行内容摘要"),
        *stamps(),
        sa.UniqueConstraint("review_id", "purchase_line_id", name="uq_review_line"),
        sa.Index("ix_review_line_purchase", "purchase_line_id"),
        sa.ForeignKeyConstraint(["review_id"], ["review_records.id"], name="fk_review_line_record"),
    )


def create_task():
    create(
        "task_supplier_groups",
        "供应商默认企微群",
        pk(),
        ref("supplier_id", comment="source_suppliers.id"),
        sa.Column("group_name", sa.String(200), nullable=False),
        sa.Column("chat_id", sa.String(190), nullable=False, comment="企微群 ID"),
        sa.Column("owner_name", sa.String(100), nullable=False),
        sa.Column("owner_userid", sa.String(190), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁"),
        sa.Column("updated_by", sa.String(200), nullable=False),
        *stamps(),
        sa.UniqueConstraint("supplier_id", name="uq_task_supplier_group"),
    )
    create(
        "task_tasks",
        "开票任务：审核通过后按 供应商 × 采购公司 × 币种 分组",
        pk(),
        ref("review_id", comment="review_records.id"),
        sa.Column("ns_account", sa.String(100), nullable=False),
        ref("customs_declaration_id", comment="冗余，便于按报关单查询"),
        sa.Column("record_no", sa.String(150), comment="冗余，CD 编号"),
        ref("supplier_id", nullable=True),
        ref("company_id", nullable=True),
        sa.Column("currency", sa.String(20)),
        sa.Column(
            "group_key",
            SHA256,
            nullable=False,
            comment="供应商 + 公司 + 币种的分组键；身份缺失时按子采购单隔离",
        ),
        sa.Column("status", sa.String(24), nullable=False, server_default="documents_pending"),
        sa.Column("completed_at", TIMESTAMP),
        *stamps(),
        sa.UniqueConstraint("review_id", "group_key", name="uq_task_review_group"),
        sa.Index("ix_task_status_supplier", "status", "supplier_id"),
        sa.Index("ix_task_declaration", "customs_declaration_id"),
        check_in(
            "ck_task_status",
            "status",
            [
                "documents_pending",
                "notify_pending",
                "awaiting_invoice",
                "partially_received",
                "completed",
                "superseded",
            ],
        ),
    )
    create(
        "task_lines",
        "任务行：每条子采购行的应开与已收",
        pk(),
        ref("task_id"),
        ref("review_line_id", comment="review_lines.id，应开值来源"),
        ref("purchase_order_id"),
        ref("purchase_line_id", comment="开票单元"),
        sa.Column("expected_quantity", QUANTITY),
        sa.Column("unit", sa.String(50)),
        sa.Column("expected_amount", AMOUNT, comment="来源金额缺失时为空，只能人工按差异结束"),
        sa.Column(
            "received_quantity",
            QUANTITY,
            nullable=False,
            server_default=sa.text("0"),
            comment="已通过分配合计（缓存）",
        ),
        sa.Column("received_amount", AMOUNT, nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("over_invoiced", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("closed_with_difference", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        generated(
            "active_purchase_line_id",
            "CASE WHEN status <> 'superseded' THEN purchase_line_id END",
            "同一子采购行只有一条有效任务行",
        ),
        *stamps(),
        sa.UniqueConstraint("active_purchase_line_id", name="uq_task_line_active"),
        sa.UniqueConstraint("task_id", "purchase_line_id", name="uq_task_line_task"),
        sa.Index("ix_task_line_purchase", "purchase_line_id"),
        sa.ForeignKeyConstraint(["task_id"], ["task_tasks.id"], name="fk_task_line_task"),
        check_in("ck_task_line_status", "status", ["open", "partial", "received", "superseded"]),
    )
    create(
        "task_documents",
        "子采购合同：只记录共享盘路径",
        pk(),
        ref("task_id"),
        ref("purchase_order_id"),
        sa.Column("order_no", sa.String(150), nullable=False),
        sa.Column("ns_environment", sa.String(100), nullable=False, comment="合同下载的 NS 环境"),
        sa.Column("ns_file_id", sa.String(40)),
        sa.Column("filename", sa.String(255)),
        sa.Column("sha256", SHA256),
        sa.Column("archive_path", sa.String(2048), comment="共享盘路径；数据库不保存文件内容"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.String(500)),
        sa.Column("archived_at", TIMESTAMP),
        *stamps(),
        sa.UniqueConstraint("task_id", "purchase_order_id", name="uq_task_document"),
        sa.ForeignKeyConstraint(["task_id"], ["task_tasks.id"], name="fk_task_document_task"),
        check_in("ck_task_document_status", "status", ["pending", "archived", "failed"]),
    )
    create(
        "task_notifications",
        "供应商开票通知：每次保存一个版本",
        pk(),
        ref("task_id"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False, server_default="manual"),
        sa.Column("chat_id", sa.String(190)),
        sa.Column("recipient_name", sa.String(200)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("sent_by", sa.String(200)),
        sa.Column("sent_at", TIMESTAMP),
        sa.Column("channel_message_id", sa.String(190), comment="企微回执，接入自动发送后填写"),
        sa.Column("created_by", sa.String(200), nullable=False),
        *stamps(),
        sa.UniqueConstraint("task_id", "version", name="uq_task_notification_version"),
        sa.ForeignKeyConstraint(["task_id"], ["task_tasks.id"], name="fk_task_notification_task"),
        check_in("ck_task_notification_channel", "channel", ["manual", "wecom"]),
        check_in("ck_task_notification_status", "status", ["draft", "sent", "failed"]),
    )
    create(
        "task_events",
        "任务状态历史，只追加",
        pk(),
        ref("task_id"),
        sa.Column("from_status", sa.String(24)),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(300)),
        sa.Column("actor", sa.String(200), nullable=False, comment="操作人或 system"),
        sa.Column("occurred_at", TIMESTAMP, nullable=False),
        *stamps(),
        sa.Index("ix_task_event_task", "task_id", "occurred_at"),
        sa.ForeignKeyConstraint(["task_id"], ["task_tasks.id"], name="fk_task_event_task"),
    )


def create_invoice():
    create(
        "invoice_raw_records",
        "柠檬云原始数据",
        pk(),
        sa.Column("source", sa.String(24), nullable=False, comment="lemon_open2 / lemon_excel"),
        sa.Column("lemon_account", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(190), nullable=False, comment="API 记录 ID；Excel 为发票去重键"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", SHA256, nullable=False),
        sa.Column("fetched_at", TIMESTAMP, nullable=False),
        *stamps(),
        sa.UniqueConstraint(
            "source", "lemon_account", "external_id", "payload_sha256", name="uq_invoice_raw_content"
        ),
    )
    create(
        "invoice_headers",
        "进项发票",
        pk(),
        sa.Column(
            "source", sa.String(24), nullable=False, comment="最近一次写入来源 lemon_open2 / lemon_excel"
        ),
        sa.Column("lemon_account", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(190), comment="柠檬云 API 记录 ID"),
        sa.Column("invoice_code", sa.String(50), comment="数电发票为空"),
        sa.Column("invoice_no", sa.String(100), nullable=False),
        sa.Column(
            "invoice_key",
            sa.String(160),
            nullable=False,
            comment="发票代码 + 号码，Excel 与 API 导入共用的去重键",
        ),
        sa.Column("invoice_date", sa.Date()),
        sa.Column("invoice_type", sa.String(100)),
        sa.Column("business_type", sa.String(100), comment="例如：采购固定资产"),
        sa.Column("status", sa.String(24), nullable=False, server_default="normal"),
        sa.Column("seller_name", sa.String(255)),
        sa.Column("seller_name_normalized", sa.String(255)),
        sa.Column("seller_tax_no", sa.String(100), comment="票面信息，保存备用"),
        sa.Column("buyer_name", sa.String(255)),
        sa.Column("buyer_name_normalized", sa.String(255)),
        sa.Column("buyer_tax_no", sa.String(100)),
        sa.Column("currency", sa.String(20), nullable=False, server_default="CNY"),
        sa.Column("amount_excluding_tax", INVOICE_AMOUNT),
        sa.Column("tax_amount", INVOICE_AMOUNT),
        sa.Column("amount_including_tax", INVOICE_AMOUNT),
        sa.Column("remark", sa.Text(), comment="备注；比对子采购单号"),
        ref("raw_record_id", nullable=True),
        sa.Column("imported_at", TIMESTAMP, nullable=False),
        *stamps(),
        sa.UniqueConstraint("lemon_account", "invoice_key", name="uq_invoice_key"),
        sa.Index("ix_invoice_date", "invoice_date"),
        sa.Index("ix_invoice_seller", "seller_name_normalized"),
        sa.ForeignKeyConstraint(["raw_record_id"], ["invoice_raw_records.id"], name="fk_invoice_raw"),
        check_in("ck_invoice_status", "status", ["normal", "red_offset", "void", "unknown"]),
    )
    create(
        "invoice_items",
        "发票行",
        pk(),
        ref("invoice_id"),
        sa.Column("source_line_key", sa.String(190), nullable=False),
        sa.Column("line_no", sa.String(40)),
        sa.Column("item_name", sa.String(500)),
        sa.Column("item_name_normalized", sa.String(500)),
        sa.Column("specification", sa.String(500)),
        sa.Column("quantity", QUANTITY),
        sa.Column("unit", sa.String(50)),
        sa.Column("unit_price", PRICE),
        sa.Column("amount_excluding_tax", INVOICE_AMOUNT),
        sa.Column("tax_rate", sa.Numeric(8, 6)),
        sa.Column("tax_amount", INVOICE_AMOUNT),
        sa.Column("amount_including_tax", INVOICE_AMOUNT),
        *stamps(),
        sa.UniqueConstraint("invoice_id", "source_line_key", name="uq_invoice_item"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoice_headers.id"], name="fk_invoice_item_header"),
    )


def create_matching():
    create(
        "matching_allocations",
        "发票行与子采购行的比对与分配",
        pk(),
        ref("invoice_id", comment="invoice_headers.id"),
        ref("invoice_item_id", comment="invoice_items.id"),
        ref("purchase_line_id", comment="source_purchase_order_lines.id"),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("amount", AMOUNT, nullable=False, comment="分配的含税金额"),
        sa.Column("status", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("confidence", sa.Numeric(5, 2), comment="0-100；人工新建时为空"),
        sa.Column("checks", sa.JSON(), comment="逐项比对：项目、发票值、采购值、结果、差额"),
        sa.Column("exceeds_expected", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "closes_purchase_line",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
            comment="人工确认该子采购行已开完（含差异）",
        ),
        sa.Column("proposed_by", sa.String(200), nullable=False, comment="system 或操作人"),
        sa.Column("proposed_at", TIMESTAMP, nullable=False),
        sa.Column("reviewed_by", sa.String(200)),
        sa.Column("reviewed_at", TIMESTAMP),
        sa.Column("review_note", sa.String(300), comment="有不一致项、超开或按差异结束时必填"),
        sa.Column("cancelled_by", sa.String(200)),
        sa.Column("cancelled_at", TIMESTAMP),
        sa.Column("cancel_reason", sa.String(300)),
        sa.Column("request_id", sa.CHAR(36), nullable=False, comment="幂等"),
        generated(
            "active_invoice_item_id",
            "CASE WHEN status IN ('proposed','confirmed') THEN invoice_item_id END",
            "同一发票行与子采购行只有一条有效记录",
        ),
        *stamps(),
        sa.UniqueConstraint("request_id", name="uq_matching_request"),
        sa.UniqueConstraint("active_invoice_item_id", "purchase_line_id", name="uq_matching_active_pair"),
        sa.Index("ix_matching_purchase", "purchase_line_id", "status"),
        sa.Index("ix_matching_invoice_item", "invoice_item_id", "status"),
        sa.Index("ix_matching_queue", "status", "confidence"),
        check_in("ck_matching_status", "status", ["proposed", "confirmed", "rejected", "cancelled"]),
    )


def create_sync():
    create(
        "sync_runs",
        "同步运行记录",
        pk(),
        sa.Column(
            "source", sa.String(32), nullable=False, comment="ns_customs / ns_purchase / lemon_invoice"
        ),
        sa.Column("account", sa.String(100), nullable=False, comment="NS 账套或柠檬云账套"),
        sa.Column("trigger_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("window_start", TIMESTAMP),
        sa.Column("window_end", TIMESTAMP),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("message", sa.Text(), comment="中文结果或失败原因，不含凭据"),
        sa.Column("started_by", sa.String(200), nullable=False, comment="操作人或 scheduler"),
        sa.Column("started_at", TIMESTAMP, nullable=False),
        sa.Column("finished_at", TIMESTAMP),
        *stamps(),
        sa.Index("ix_sync_run_source", "source", "account", "started_at"),
        check_in("ck_sync_run_status", "status", ["running", "succeeded", "partial", "failed"]),
        check_in("ck_sync_run_trigger", "trigger_type", ["schedule", "manual"]),
    )
    create(
        "sync_cursors",
        "增量同步水位",
        sa.Column("source", sa.String(32), primary_key=True),
        sa.Column("account", sa.String(100), primary_key=True),
        sa.Column("last_modified_at", TIMESTAMP, comment="已完整处理的来源修改时间水位"),
        ref("last_run_id", nullable=True),
        *stamps(),
        sa.ForeignKeyConstraint(["last_run_id"], ["sync_runs.id"], name="fk_sync_cursor_run"),
    )


def upgrade():
    create_source()
    create_review()
    create_task()
    create_invoice()
    create_matching()
    create_sync()


def downgrade():
    for name in reversed(TABLES):
        op.drop_table(name)
