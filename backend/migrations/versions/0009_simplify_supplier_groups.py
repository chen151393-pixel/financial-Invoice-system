"""简化供应商群配置，仅保留当前供应商映射。"""

from alembic import op

revision = "0009_simplify_supplier_groups"
down_revision = "0008_contract_metadata"
branch_labels = None
depends_on = None


def upgrade():
    # 按产品简化要求移除辅助数据；当前供应商映射及任务通知记录保持原样。
    op.drop_table("finance_supplier_group_history")
    op.drop_table("finance_wecom_group_directory")


def downgrade():
    raise RuntimeError("已删除的群目录与配置历史无法恢复，请使用备份或增量迁移")
