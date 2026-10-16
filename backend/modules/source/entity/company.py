"""采购公司（NS 子公司 / 分类），与发票购买方比对。"""

from sqlalchemy import Boolean, Column, String, Table, UniqueConstraint, text

from backend.core.schema import ID, schema_metadata, table_options, timestamps

companies = Table(
    "source_companies",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column("ns_account", String(100), comment="NS 账套标识，用于隔离正式、沙箱等来源", nullable=False),
    Column(
        "ns_internal_id",
        String(190),
        comment="NS 来源身份；与账套组合识别记录。公司身份可能带记录类型前缀",
        nullable=False,
    ),
    Column("name", String(255), comment="来源公司或申报主体名称原文", nullable=False),
    Column(
        "name_normalized",
        String(255),
        comment="规范化后的名称，用于搜索、比对，不代替原名展示",
        nullable=False,
    ),
    Column(
        "is_active",
        Boolean,
        comment="当前是否有效；停用保留历史记录，不物理删除",
        nullable=False,
        server_default=text("1"),
    ),
    *timestamps(),
    UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_company_ns"),
    comment="采购公司（NS 子公司），与发票购买方比对",
    **table_options,
)
