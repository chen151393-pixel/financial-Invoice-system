"""review：海关回执（按出口报关单号保存海关明细、境外收货人与 NS 比对结果）。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP, identifier, table_options, timestamps
from sqlalchemy import (
    CHAR,
    JSON,
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

revision = "0042_review_customs_receipts"
down_revision = "0041_identity_role_pages"
branch_labels = None
depends_on = None
metadata = MetaData()

customs_receipts = Table(
    "review_customs_receipts",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="海关回执本地主键"),
    Column("declaration_no", identifier(150), nullable=False, comment="海关出口报关单号，即 NS 真实报关单号"),
    Column("revision", Integer, nullable=False, comment="当前明细版本号；内容变化的重新导入递增"),
    Column(
        "content_sha256", CHAR(64), nullable=False, comment="当前版本回执内容摘要，相同内容重复导入不换版"
    ),
    Column("export_date", Date, comment="出口日期（海关回执）"),
    Column("consignee", String(500), comment="境外收货人（仅来自海关回执；回执为空时为 NULL）"),
    Column("file_name", String(255), nullable=False, comment="当前版本来源文件名"),
    Column("imported_by", String(190), nullable=False, comment="当前版本导入人（认证身份）"),
    Column("imported_at", TIMESTAMP, nullable=False, comment="当前版本导入时间，UTC"),
    Column(
        "ns_declaration_id",
        ID,
        comment="匹配到的 NS 报关单本地 ID（source_customs_declarations.id，跨模块不建外键）",
    ),
    Column(
        "match_status",
        String(24),
        nullable=False,
        comment="比对结果：matched 一致；split_matched 拆行/合并后一致；different 有差异；"
        "ns_missing 未找到 NS 报关单；ns_duplicate NS 有多张同号报关单",
    ),
    Column("match_result", JSON, comment="比对明细（分组、NS 报关行快照与差异说明），用于展示"),
    Column("matched_at", TIMESTAMP, nullable=False, comment="最近一次比对时间，UTC"),
    *timestamps(),
    UniqueConstraint("declaration_no", name="uq_review_customs_receipt_no"),
    Index("ix_review_customs_receipt_status", "match_status"),
    Index("ix_review_customs_receipt_export", "export_date"),
    CheckConstraint(
        "match_status IN ('matched','split_matched','different','ns_missing','ns_duplicate')",
        name="ck_review_customs_receipt_status",
    ),
    comment="海关回执报关单头与比对结果",
    **table_options,
)

customs_receipt_lines = Table(
    "review_customs_receipt_lines",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="海关回执明细本地主键"),
    Column(
        "receipt_id",
        ID,
        ForeignKey("review_customs_receipts.id", name="fk_review_customs_receipt_line_head"),
        nullable=False,
        comment="所属海关回执，指向 review_customs_receipts.id",
    ),
    Column("revision", Integer, nullable=False, comment="所属回执版本号"),
    Column("item_no", String(20), nullable=False, comment="项号（两位数字文本）"),
    Column("source_row", Integer, nullable=False, comment="来源文件中的行号，便于核对"),
    Column("hs_code", String(20), comment="商品代码"),
    Column("name", String(500), nullable=False, comment="海关商品名称"),
    Column("specification", String(500), comment="规格型号"),
    Column("contract_no", String(100), comment="出口合同号"),
    Column("tax_type", String(40), comment="征免类型，如征税、退税"),
    Column("check_status", String(40), comment="数据检查状态"),
    Column("deal_unit", String(50), nullable=False, comment="成交单位，与 NS 报关单位比较"),
    Column("deal_quantity", Numeric(26, 8), nullable=False, comment="成交数量，与 deal_unit 配套"),
    Column("currency", String(20), comment="成交币制"),
    Column("deal_total", Numeric(24, 6), comment="成交总价，与 currency 配套"),
    Column("usd_fob", Numeric(24, 6), comment="美元离岸价"),
    Column("legal_unit", String(50), comment="法定单位，仅展示不参与比对"),
    Column("legal_quantity", Numeric(26, 8), comment="法定数量，与 legal_unit 配套，仅展示"),
    Column("customs_doc", String(20), comment="关单信息，如存在、不存在"),
    Column("usage_flag", String(20), comment="使用标志，如未使用"),
    *timestamps(),
    UniqueConstraint("receipt_id", "revision", "item_no", name="uq_review_customs_receipt_line"),
    comment="海关回执报关明细，按版本保留",
    **table_options,
)


def upgrade():
    customs_receipts.create(op.get_bind())
    customs_receipt_lines.create(op.get_bind())


def downgrade():
    # 已导入的回执含境外收货人，降级删除会丢失；仅空表允许回退。
    if not op.get_context().as_sql:
        if op.get_bind().execute(sa.text("SELECT 1 FROM review_customs_receipts")).first():
            raise RuntimeError("海关回执已有数据（含境外收货人），不能降级删除；请保留数据")
    customs_receipt_lines.drop(op.get_bind())
    customs_receipts.drop(op.get_bind())
