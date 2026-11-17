"""settlement：结汇批次与批次明细（香港中转 / 直接收汇两种回款路径）。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP, identifier, table_options, timestamps
from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)

revision = "0045_settlement_batches"
down_revision = "0044_review_dual_approval"
branch_labels = None
depends_on = None
metadata = MetaData()

batches = Table(
    "settlement_batches",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="结汇批次本地主键"),
    Column("batch_no", identifier(40), comment="批次号，如 SB20261117-00001；插入后按主键生成"),
    Column("request_id", identifier(64), nullable=False, comment="创建请求幂等号，重复提交返回同一批次"),
    Column(
        "route",
        String(20),
        nullable=False,
        comment="回款路径：hk_transit 贸易国为香港的中转结汇；direct 贸易国为真实客户国家的直接收汇",
    ),
    Column(
        "status",
        String(20),
        nullable=False,
        comment="状态：collected 已收款；documents_ready 资料已出（仅香港中转）；settled 已结汇；cancelled 已作废",
    ),
    Column("consignee", String(500), nullable=False, comment="境外收货人（批次内各报关单一致）"),
    Column("currency", String(20), nullable=False, comment="币种代码，批次内各报关单一致"),
    Column(
        "declared_total", Numeric(24, 6), nullable=False, comment="批次内报关单成交总价合计，与 currency 配套"
    ),
    Column("payer", String(500), comment="付款方（银行水单）；直接收汇时应与境外收货人一致"),
    Column("receiving_account", String(200), comment="收款账户（香港账户或境内账户）"),
    Column("received_on", Date, nullable=False, comment="到账日期"),
    Column("received_amount", Numeric(24, 6), nullable=False, comment="实际到账金额，与 currency 配套"),
    Column("received_fee", Numeric(24, 6), nullable=False, comment="到账环节银行手续费"),
    Column("received_reference", String(200), comment="到账流水号、NS 收款单号等凭证号"),
    Column("remitted_on", Date, comment="香港汇回境内日期（仅香港中转）"),
    Column("remitted_amount", Numeric(24, 6), comment="香港汇回境内实际到账金额（仅香港中转）"),
    Column("remitted_fee", Numeric(24, 6), comment="汇回环节银行手续费（仅香港中转）"),
    Column("remitted_reference", String(200), comment="汇回流水号（仅香港中转）"),
    Column("note", String(500), comment="经办说明"),
    Column("created_by", String(190), nullable=False, comment="创建人（认证身份）"),
    Column("documents_ready_by", String(190), comment="确认资料已出的操作人"),
    Column("documents_ready_at", TIMESTAMP, comment="确认资料已出时间，UTC"),
    Column("settled_by", String(190), comment="确认已结汇的操作人"),
    Column("settled_at", TIMESTAMP, comment="确认已结汇时间，UTC"),
    Column("cancelled_by", String(190), comment="作废人"),
    Column("cancelled_at", TIMESTAMP, comment="作废时间，UTC"),
    Column("cancel_reason", String(300), comment="作废原因"),
    *timestamps(),
    UniqueConstraint("request_id", name="uq_settlement_batch_request"),
    UniqueConstraint("batch_no", name="uq_settlement_batch_no"),
    Index("ix_settlement_batch_status", "route", "status"),
    Index("ix_settlement_batch_received", "received_on"),
    CheckConstraint("route IN ('hk_transit','direct')", name="ck_settlement_batch_route"),
    CheckConstraint(
        "status IN ('collected','documents_ready','settled','cancelled')", name="ck_settlement_batch_status"
    ),
    comment="结汇批次：一笔回款及其对应的报关单合计、手续费与汇回记录",
    **table_options,
)

items = Table(
    "settlement_batch_items",
    metadata,
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


def upgrade():
    batches.create(op.get_bind())
    items.create(op.get_bind())


def downgrade():
    # 结汇批次是银行收汇与汇回的业务凭证，有数据时不允许降级删除。
    if not op.get_context().as_sql:
        if op.get_bind().execute(sa.text("SELECT 1 FROM settlement_batches")).first():
            raise RuntimeError("结汇批次已有数据，不能降级删除；请保留数据")
    items.drop(op.get_bind())
    batches.drop(op.get_bind())
