"""进项发票票头。"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

headers = Table(
    "invoice_headers",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "source",
        String(24),
        nullable=False,
        comment="来源渠道：lemon_excel 柠檬云 Excel；lemon_open2 柠檬云接口（待接入）",
    ),
    Column(
        "lemon_account",
        String(100),
        comment="柠檬云来源账套命名空间；当前 Excel 固定为 lemon，不能直接视为任意 API 账套",
        nullable=False,
    ),
    Column("external_id", String(190), comment="柠檬云 API 发票记录 ID；当前 Excel 导入票头可为空"),
    Column("invoice_code", String(50), comment="发票代码；当前数电发票没有该代码，可为空"),
    Column("invoice_no", String(100), comment="发票号码，按字符串保存，避免数字精度损失", nullable=False),
    Column(
        "invoice_key",
        String(160),
        nullable=False,
        comment="发票代码与号码以冒号分隔的稳定去重键；在 lemon_account 范围内唯一",
    ),
    Column("invoice_date", Date, comment="开票日期"),
    Column("invoice_type", String(100), comment="票种名称"),
    Column("business_type", String(100), comment="业务类型，例如采购固定资产；当前 Excel 导入仅接受该类型"),
    Column(
        "status",
        String(24),
        comment="票面状态：normal 正常；red_offset 红冲；void 作废；unknown 未知",
        nullable=False,
        server_default="normal",
    ),
    Column("seller_name", String(255), comment="票面销售方名称，对照 NS 供应商"),
    Column("seller_name_normalized", String(255), comment="规范化销售方名称，用于供应商比对"),
    Column("seller_tax_no", String(100), comment="销售方纳税人识别号；NS 供应商当前无对应税号列，保留备用"),
    Column("buyer_name", String(255), comment="票面购买方名称，对照采购公司；当前 Excel 未提供时为空"),
    Column("buyer_name_normalized", String(255), comment="规范化购买方名称"),
    Column("buyer_tax_no", String(100), comment="购买方纳税人识别号"),
    Column(
        "currency",
        String(20),
        comment="业务币种代码，例如 CNY；不是汇率",
        nullable=False,
        server_default="CNY",
    ),
    Column("amount_excluding_tax", Numeric(18, 2), comment="不含税金额；票头为整票，商品行为该行"),
    Column("tax_amount", Numeric(18, 2), comment="税额；票头为整票，商品行为该行"),
    Column("amount_including_tax", Numeric(18, 2), comment="价税合计；票头为整票，商品行为该行"),
    Column("remark", Text, comment="票面备注；用于提取、比对子采购单号"),
    Column(
        "raw_record_id",
        ID,
        ForeignKey("invoice_raw_records.id", name="fk_invoice_raw"),
        comment="对应原始数据版本 ID；source 表指向 source_raw_records，invoice 表指向 invoice_raw_records",
    ),
    Column("imported_at", TIMESTAMP, comment="最近一次导入该发票的时间，UTC", nullable=False),
    Column(
        "current_version_id",
        ID,
        comment="当前发票不可变版本 ID，逻辑指向 invoice_versions.id；票头和商品行是当前查询投影",
    ),
    Column(
        "detail_status",
        String(24),
        comment="明细完整性：pending 待补齐；complete 完整；failed 失败或身份待核实",
        nullable=False,
        server_default="complete",
    ),
    *timestamps(),
    UniqueConstraint("lemon_account", "invoice_key", name="uq_invoice_key"),
    Index("ix_invoice_date", "invoice_date"),
    Index("ix_invoice_seller", "seller_name_normalized"),
    CheckConstraint("status IN ('normal','red_offset','void','unknown')", name="ck_invoice_status"),
    comment="进项发票",
    **table_options,
)
