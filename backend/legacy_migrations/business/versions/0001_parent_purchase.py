"""在现有六表基础上增加母采购两表及母子外键，不回填推测关联。"""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

revision = "0001_business_parents"
down_revision = None
branch_labels = None
depends_on = None

BASE_TABLES = (
    "purchase_orders",
    "purchase_order_lines",
    "customs_declarations",
    "customs_declaration_lines",
    "invoices",
    "invoice_lines",
)


def bigint():
    return mysql.BIGINT(unsigned=True)


def identity_columns():
    return [
        sa.Column("id", bigint(), primary_key=True, autoincrement=True, comment="本地主键"),
        sa.Column("tenant_id", sa.String(100), nullable=False, comment="服务端确定的数据归属"),
    ]


def preflight():
    inspector = sa.inspect(op.get_bind())
    names = set(inspector.get_table_names())
    if set(BASE_TABLES) - names:
        raise RuntimeError("业务迁移要求已有六张基础表，不会自动初始化未知数据库")
    if names & {"parent_purchase_orders", "parent_purchase_order_lines"}:
        raise RuntimeError("存在未登记的母采购表或中断迁移，请先核实结构，不覆盖已有表")
    for name in ("purchase_orders", "purchase_order_lines"):
        columns = {column["name"]: column for column in inspector.get_columns(name)}
        if "parent_purchase_order_id" in columns or "parent_purchase_order_line_id" in columns:
            raise RuntimeError("母采购关联字段已存在，请核实是否有中断迁移")
        if not isinstance(columns["id"]["type"], mysql.BIGINT) or not columns["id"]["type"].unsigned:
            raise RuntimeError("业务表主键须为 BIGINT UNSIGNED，请先核实结构")
        tenant = columns["tenant_id"]["type"]
        if tenant.length != 100 or tenant.collation != "utf8mb4_bin":
            raise RuntimeError("业务表租户字段类型与预期不一致，请先核实结构")


def upgrade():
    if not context.is_offline_mode():
        preflight()
    op.create_table(
        "parent_purchase_orders",
        *identity_columns(),
        sa.Column("ns_account", sa.String(100), nullable=False, comment="NS账户"),
        sa.Column("ns_record_type", sa.String(100), nullable=False, comment="经核实的NS母单记录类型"),
        sa.Column("ns_internal_id", sa.String(190), nullable=False, comment="NS母单内部ID"),
        sa.Column("order_no", sa.String(150), comment="母采购单号"),
        sa.Column("order_date", sa.Date(), comment="母采购业务日期"),
        sa.Column("supplier_identifier", sa.String(100), comment="NS供应商引用"),
        sa.Column("supplier_name", sa.String(255), comment="供应商名称"),
        sa.Column("company_identifier", sa.String(100), comment="NS公司类型及内部ID"),
        sa.Column("company_name", sa.String(255), comment="公司抬头"),
        sa.Column("currency_code", sa.String(20), comment="来源币种"),
        sa.Column("total_amount", sa.Numeric(24, 6), comment="母单总金额，不与子单金额重复相加"),
        sa.Column("source_status", sa.String(100), comment="NS原始业务状态"),
        sa.Column("source_data", mysql.JSON(), nullable=False, comment="完整单头和明细原始快照"),
        sa.Column("source_modified_at", mysql.DATETIME(fsp=6), comment="来源修改时间UTC"),
        sa.Column("synced_at", mysql.DATETIME(fsp=6), comment="当前完整快照保存时间UTC"),
        sa.Column("last_complete_sync_at", mysql.DATETIME(fsp=6), comment="最近完整同步时间UTC"),
        sa.Column(
            "detail_sync_status",
            sa.String(16),
            nullable=False,
            server_default="pending",
            comment="明细同步状态",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1", comment="来源有效标识"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_parent_purchase_tenant_id"),
        sa.UniqueConstraint("tenant_id", "ns_account", "id", name="uq_parent_purchase_account_id"),
        sa.UniqueConstraint(
            "tenant_id", "ns_account", "ns_record_type", "ns_internal_id", name="uq_parent_purchase_ns_source"
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(TRIM(ns_account)) > 0 AND CHAR_LENGTH(TRIM(ns_record_type)) > 0 AND CHAR_LENGTH(TRIM(ns_internal_id)) > 0",
            name="ck_parent_purchase_source",
        ),
        sa.CheckConstraint(
            "detail_sync_status IN ('pending','complete','failed')", name="ck_parent_purchase_sync"
        ),
        sa.CheckConstraint("is_active IN (0,1)", name="ck_parent_purchase_active"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        comment="母采购单主表，当前阶段只建结构，来源读取另行接入",
    )
    op.create_index(
        "ix_parent_purchase_number", "parent_purchase_orders", ["tenant_id", "ns_account", "order_no"]
    )
    op.create_table(
        "parent_purchase_order_lines",
        *identity_columns(),
        sa.Column("parent_purchase_order_id", bigint(), nullable=False, comment="所属母采购单ID"),
        sa.Column(
            "source_line_key", sa.String(190), nullable=False, comment="稳定来源行键，不使用展示数组下标"
        ),
        sa.Column("line_no", sa.String(40), comment="显示行号"),
        sa.Column("item_code", sa.String(150), comment="商品编码"),
        sa.Column("item_name", sa.String(500), comment="商品名称"),
        sa.Column("declaration_name", sa.String(500), comment="来源报关品名"),
        sa.Column("specification", sa.String(500), comment="规格型号"),
        sa.Column("quantity", sa.Numeric(26, 8), comment="母采购数量"),
        sa.Column("unit_name", sa.String(50), comment="采购单位"),
        sa.Column("tax_inclusive_price", sa.Numeric(24, 8), comment="核实含税口径后的采购单价"),
        sa.Column("amount", sa.Numeric(24, 6), comment="来源行金额"),
        sa.Column("source_data", mysql.JSON(), nullable=False, comment="原始来源行快照"),
        sa.Column("synced_at", mysql.DATETIME(fsp=6), comment="成功同步时间UTC"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1", comment="来源有效标识"),
        sa.UniqueConstraint(
            "tenant_id", "parent_purchase_order_id", "source_line_key", name="uq_parent_purchase_line_source"
        ),
        sa.UniqueConstraint(
            "tenant_id", "parent_purchase_order_id", "id", name="uq_parent_purchase_line_parent_id"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_purchase_order_id"],
            ["parent_purchase_orders.tenant_id", "parent_purchase_orders.id"],
            name="fk_parent_purchase_line_head",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.CheckConstraint("CHAR_LENGTH(TRIM(source_line_key)) > 0", name="ck_parent_purchase_line_key"),
        sa.CheckConstraint("is_active IN (0,1)", name="ck_parent_purchase_line_active"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        comment="母采购单来源明细",
    )
    op.add_column(
        "purchase_orders",
        sa.Column(
            "parent_purchase_order_id", bigint(), nullable=True, comment="关联母采购单ID，来源未核实前为空"
        ),
    )
    op.create_unique_constraint(
        "uq_purchase_parent_link", "purchase_orders", ["tenant_id", "id", "parent_purchase_order_id"]
    )
    op.create_foreign_key(
        "fk_purchase_parent_account",
        "purchase_orders",
        "parent_purchase_orders",
        ["tenant_id", "ns_account", "parent_purchase_order_id"],
        ["tenant_id", "ns_account", "id"],
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column(
            "parent_purchase_order_id",
            bigint(),
            nullable=True,
            comment="母单ID冗余，仅用于约束母行与子单归属一致",
        ),
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column(
            "parent_purchase_order_line_id", bigint(), nullable=True, comment="来源母采购明细ID，未核实前为空"
        ),
    )
    op.create_check_constraint(
        "ck_purchase_line_parent_pair",
        "purchase_order_lines",
        "(parent_purchase_order_id IS NULL AND parent_purchase_order_line_id IS NULL) OR (parent_purchase_order_id IS NOT NULL AND parent_purchase_order_line_id IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_purchase_line_parent_header",
        "purchase_order_lines",
        "purchase_orders",
        ["tenant_id", "purchase_order_id", "parent_purchase_order_id"],
        ["tenant_id", "id", "parent_purchase_order_id"],
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )
    op.create_foreign_key(
        "fk_purchase_line_parent_line",
        "purchase_order_lines",
        "parent_purchase_order_lines",
        ["tenant_id", "parent_purchase_order_id", "parent_purchase_order_line_id"],
        ["tenant_id", "parent_purchase_order_id", "id"],
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )


def downgrade():
    raise RuntimeError("母采购表可能已有业务数据，不提供自动删表降级；需另行审阅保留数据的变更")
