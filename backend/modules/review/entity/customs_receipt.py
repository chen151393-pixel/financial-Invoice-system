"""海关回执：按出口报关单号保存海关返回的报关明细，并记录与 NS 报关单的比对结果。

境外收货人只来自海关回执（NS 报关单没有该字段），随回执保存；匹配到 NS 报关单后记录其 ID。
重新导入同一报关单号时版本号加 1，旧版本明细保留，不物理删除。
"""

from sqlalchemy import (
    CHAR,
    JSON,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)

from backend.core.schema import ID, TIMESTAMP, identifier, schema_metadata, table_options, timestamps

MATCH_STATUSES = ("matched", "split_matched", "different", "ns_missing", "ns_duplicate")

customs_receipts = Table(
    "review_customs_receipts",
    schema_metadata,
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
    schema_metadata,
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
