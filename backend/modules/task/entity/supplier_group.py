"""供应商默认企微群。"""

from sqlalchemy import Boolean, Column, Integer, String, Table, UniqueConstraint, text

from backend.core.schema import ID, schema_metadata, table_options, timestamps

supplier_groups = Table(
    "task_supplier_groups",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("supplier_id", ID, nullable=False, comment="source_suppliers.id"),
    Column("group_name", String(200), nullable=False),
    Column("chat_id", String(190), nullable=False, comment="企微群 ID"),
    Column("owner_name", String(100), nullable=False),
    Column("owner_userid", String(190), nullable=False),
    Column("enabled", Boolean, nullable=False, server_default=text("1")),
    Column("version", Integer, nullable=False, server_default=text("1"), comment="乐观锁"),
    Column("updated_by", String(200), nullable=False),
    *timestamps(),
    UniqueConstraint("supplier_id", name="uq_task_supplier_group"),
    comment="供应商默认企微群",
    **table_options,
)
