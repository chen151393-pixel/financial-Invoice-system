"""销售单：同步时按子采购单关联读取单头（币种、汇率），报关申报价据此换算为人民币。"""

from sqlalchemy import Column, Numeric, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

sales_orders = Table(
    "source_sales_orders",
    schema_metadata,
    Column(
        "id", ID, primary_key=True, autoincrement=True, comment="本地自增主键；与 NS 内部 ID、单号分开保存"
    ),
    Column("ns_account", String(100), nullable=False, comment="NS 账套标识，用于隔离正式、沙箱等来源"),
    Column("ns_internal_id", String(190), nullable=False, comment="NS 销售单内部 ID"),
    Column("order_no", String(150), comment="销售单号（NS tranid），与报关行销售订单号对照"),
    Column("currency", String(20), comment="币种代码，例如 USD；无法识别时为空"),
    Column("currency_name", String(100), comment="NS 返回的币种名称原文，供追溯"),
    Column(
        "exchange_rate",
        Numeric(28, 12),
        comment="NS exchangerate：1 单位本币种折合人民币；缺失为空，不以 1 代替",
    ),
    Column("synced_at", TIMESTAMP, nullable=False, comment="本次成功保存来源数据的时间，UTC"),
    *timestamps(),
    UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_sales_ns"),
    comment="销售单单头（币种、汇率），用于申报幅度与发票价格校验；不参与报关单内容摘要",
    **table_options,
)
