"""task：供应商档案"是否开启供应商通知"，人工维护，默认开启。

没有记录的供应商视为开启；关闭后财务审核通过时不再为该供应商生成开票任务（只影响之后的审核）。
"""

from alembic import op
from backend.core.schema import ID, table_options, timestamps
from sqlalchemy import Boolean, Column, Integer, String, UniqueConstraint, text

revision = "0026_task_supplier_settings"
down_revision = "0025_sync_merge_lemon_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_supplier_settings",
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


def downgrade():
    raise RuntimeError("供应商设置为人工维护数据，不能降级删除；请保留数据")
