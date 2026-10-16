"""供应商默认企微群。"""

from sqlalchemy import Boolean, Column, Integer, String, Table, UniqueConstraint, text

from backend.core.schema import ID, schema_metadata, table_options, timestamps

supplier_groups = Table(
    "task_supplier_groups",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column("supplier_id", ID, nullable=False, comment="供应商本地主键，指向 source_suppliers.id"),
    Column("group_name", String(200), comment="供应商默认企业微信群名称", nullable=False),
    Column("chat_id", String(190), nullable=False, comment="企业微信群 ID；不能把群名称当作群身份"),
    Column("owner_name", String(100), comment="群主或负责人的显示姓名", nullable=False),
    Column("owner_userid", String(190), comment="群主或负责人的企业微信用户 ID", nullable=False),
    Column("enabled", Boolean, comment="该供应商群配置是否启用", nullable=False, server_default=text("1")),
    Column(
        "version",
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="供应商群配置乐观锁版本，防止并发编辑覆盖",
    ),
    Column("updated_by", String(200), comment="最后修改配置的认证操作者", nullable=False),
    *timestamps(),
    UniqueConstraint("supplier_id", name="uq_task_supplier_group"),
    comment="供应商默认企微群",
    **table_options,
)
