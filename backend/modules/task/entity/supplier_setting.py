"""供应商档案人工设置：是否开启供应商通知。"""

from sqlalchemy import Boolean, Column, Integer, String, Table, UniqueConstraint, text

from backend.core.schema import ID, schema_metadata, table_options, timestamps

supplier_settings = Table(
    "task_supplier_settings",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="供应商设置主键"),
    Column("supplier_id", ID, nullable=False, comment="供应商本地主键，指向 source_suppliers.id"),
    Column(
        "notify_enabled",
        Boolean,
        nullable=False,
        server_default=text("1"),
        comment="是否开启供应商通知；关闭后审核通过不生成该供应商的开票任务",
    ),
    Column(
        "version",
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="设置乐观锁版本，防止并发编辑覆盖",
    ),
    Column("updated_by", String(200), nullable=False, comment="最后修改设置的认证操作者"),
    *timestamps(),
    UniqueConstraint("supplier_id", name="uq_task_supplier_setting"),
    comment="供应商档案人工设置：是否开启供应商通知",
    **table_options,
)
