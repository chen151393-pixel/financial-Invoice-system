"""identity：角色页面范围；已有人员和角色绑定不变。有配置时拒绝降级丢弃授权。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, table_options, timestamps

revision = "0041_identity_role_pages"
down_revision = "0040_sync_ns_plans"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "identity_role_pages",
        sa.Column("id", ID, primary_key=True, autoincrement=True, comment="角色页面配置主键"),
        sa.Column("role", sa.String(40), nullable=False, comment="固定角色代码；管理员页面权限不可修改"),
        sa.Column("pages", sa.JSON, nullable=False, comment="允许访问的页面代码数组；空数组为无权限"),
        sa.Column("revision", sa.Integer, nullable=False, comment="编辑版本；未配置时接口版本为 0"),
        sa.Column("updated_by", sa.String(200), nullable=False, comment="最近保存的认证管理员"),
        *timestamps(),
        sa.UniqueConstraint("role", name="uq_identity_role_pages_role"),
        comment="角色的页面访问范围，多角色取并集，独立于具体业务操作权限",
        **table_options,
    )


def downgrade():
    if not op.get_context().as_sql:
        if op.get_bind().execute(sa.text("SELECT 1 FROM identity_role_pages")).first():
            raise RuntimeError("已有角色页面权限配置，不能降级删除授权范围；请保留数据")
    op.drop_table("identity_role_pages")
