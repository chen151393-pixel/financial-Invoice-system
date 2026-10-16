"""供应商（NS vendor）。"""

from sqlalchemy import Boolean, Column, Index, String, Table, UniqueConstraint, text

from backend.core.schema import ID, schema_metadata, table_options, timestamps

suppliers = Table(
    "source_suppliers",
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
    Column("name", String(255), comment="NS 供应商名称原文，用于对照发票销售方", nullable=False),
    Column(
        "name_normalized",
        String(255),
        nullable=False,
        comment="规范化后的名称，用于搜索、比对，不代替原名展示",
    ),
    Column(
        "is_active",
        Boolean,
        comment="当前是否有效；停用保留历史记录，不物理删除",
        nullable=False,
        server_default=text("1"),
    ),
    *timestamps(),
    UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_supplier_ns"),
    Index("ix_source_supplier_name", "ns_account", "name_normalized"),
    comment="供应商（NS vendor）",
    **table_options,
)
