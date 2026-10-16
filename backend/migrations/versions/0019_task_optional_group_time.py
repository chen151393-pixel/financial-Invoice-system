"""task：创建时间可缺省；无法降级为必填，以免伪造或丢弃已导入群资料。"""

from alembic import op
from backend.core.schema import TIMESTAMP

revision = "0019_task_optional_group_time"
down_revision = "0018_sync_lemon_runs"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("task_external_groups") as batch:
        batch.alter_column(
            "group_created_at",
            existing_type=TIMESTAMP,
            nullable=True,
            existing_comment="群创建时间，UTC",
        )


def downgrade():
    raise RuntimeError("不能降级删除或伪造缺少创建时间的外部群资料")
