"""task：群人数可缺省；无法降级为必填，以免伪造或丢弃已导入群资料。"""

from alembic import op
from sqlalchemy import Integer

revision = "0020_task_optional_group_count"
down_revision = "0019_task_optional_group_time"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("task_external_groups") as batch:
        batch.alter_column(
            "member_count",
            existing_type=Integer(),
            nullable=True,
            existing_comment="导入时群人数",
        )


def downgrade():
    raise RuntimeError("不能降级删除或伪造缺少群人数的外部群资料")
