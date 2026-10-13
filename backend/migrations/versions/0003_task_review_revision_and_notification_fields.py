"""task：任务记录审核版本；通知记录发送员工与人工登记说明。

- task_tasks.review_revision：生成任务的审核版本，开票跟进页展示"审核版本 N"（审核模块不对 task 开放读取）。
- task_notifications.sender_name：负责在企微外部群发送的员工（人工填写或取自供应商默认群群主）。
- task_notifications.note：人工登记发送时填写的说明。
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_task_review_revision_and_notification_fields"
down_revision = "0002_source_purchase_parent_order_no"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("task_tasks") as batch:
        batch.add_column(
            sa.Column(
                "review_revision",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
                comment="生成任务的审核版本",
            )
        )
    with op.batch_alter_table("task_notifications") as batch:
        batch.add_column(sa.Column("sender_name", sa.String(100), comment="负责发送的员工"))
        batch.add_column(sa.Column("note", sa.String(500), comment="人工登记发送说明"))


def downgrade():
    with op.batch_alter_table("task_notifications") as batch:
        batch.drop_column("note")
        batch.drop_column("sender_name")
    with op.batch_alter_table("task_tasks") as batch:
        batch.drop_column("review_revision")
