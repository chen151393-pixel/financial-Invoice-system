"""结汇批次：一笔回款对应一组报关单。

香港中转（hk_transit）：香港账户收款建批次 → 资料已出 → 香港汇回境内对平后已结汇；批次与汇回一一对应。
直接收汇（direct）：境内收款（NS 已核销）登记后，到账加手续费等于报关合计即已结汇。
差额只认手续费：到账金额 + 手续费 = 报关金额，严格相等才通过。
"""

from sqlalchemy import CheckConstraint, Column, Date, Index, Numeric, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, identifier, schema_metadata, table_options, timestamps

ROUTES = ("hk_transit", "direct")
STATUSES = ("collected", "documents_ready", "settled", "cancelled")

settlement_batches = Table(
    "settlement_batches",
    schema_metadata,
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
