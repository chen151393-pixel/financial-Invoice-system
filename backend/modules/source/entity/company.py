"""采购公司（NS 子公司 / 分类），与发票购买方比对。"""

from sqlalchemy import Boolean, Column, String, Table, UniqueConstraint, text

from backend.core.schema import ID, schema_metadata, table_options, timestamps

companies = Table(
    "source_companies",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("ns_account", String(100), nullable=False),
    Column("ns_internal_id", String(190), nullable=False),
    Column("name", String(255), nullable=False),
    Column("name_normalized", String(255), nullable=False),
    Column("is_active", Boolean, nullable=False, server_default=text("1")),
    *timestamps(),
    UniqueConstraint("ns_account", "ns_internal_id", name="uq_source_company_ns"),
    comment="采购公司（NS 子公司），与发票购买方比对",
    **table_options,
)
