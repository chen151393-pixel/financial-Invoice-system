"""MySQL业务库的供应商群映射；应用库元数据仅用于历史迁移兼容。"""

from sqlalchemy import BigInteger, Boolean, Column, Integer, String, Table, UniqueConstraint

from backend.core.schema import identifier, metadata, table_options

bindings = Table(
    "finance_supplier_groups",
    metadata,
    Column("owner", identifier(200), primary_key=True),
    Column("account", identifier(100), primary_key=True),
    Column("supplier_id", identifier(190), primary_key=True),
    Column("supplier_key", identifier(64), nullable=False),
    Column("supplier_name", String(255), nullable=False),
    Column("group_name", String(200), nullable=False),
    Column("chat_id", identifier(190), nullable=False),
    Column("employee", String(100), nullable=False),
    Column("userid", identifier(190), nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
    UniqueConstraint("owner", "account", "supplier_key", name="uq_supplier_group_key"),
    **table_options,
)
