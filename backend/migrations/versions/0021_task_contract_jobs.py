"""task：审核事务登记合同自动归档队列，保留历史任务与合同记录。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, table_options, timestamps

revision = "0021_task_contract_jobs"
down_revision = "0020_task_optional_group_count"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_contract_jobs",
        sa.Column("id", ID, primary_key=True, autoincrement=True, comment="合同归档作业主键"),
        sa.Column(
            "task_id",
            ID,
            sa.ForeignKey("task_tasks.id", name="fk_task_contract_job_task"),
            nullable=False,
            comment="开票任务 ID",
        ),
        sa.Column("purchase_order_id", ID, nullable=False, comment="子采购单 ID，不建立跨模块外键"),
        sa.Column("actor", sa.String(190), nullable=False, comment="触发自动归档的财务审核身份"),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            comment="pending待处理；completed已归档；failed失败待人工重试",
        ),
        sa.Column("error_message", sa.String(500), comment="脱敏失败原因，成功后清空"),
        *timestamps(),
        sa.UniqueConstraint("task_id", "purchase_order_id", name="uq_task_contract_job"),
        sa.CheckConstraint("status IN ('pending','completed','failed')", name="ck_task_contract_job_status"),
        comment="财务审核提交后的合同自动归档队列，不保存 PDF",
        **table_options,
    )
    op.create_index("ix_task_contract_job_pending", "task_contract_jobs", ["status", "id"])


def downgrade():
    raise RuntimeError("合同队列可能存在待处理记录，不能降级删除；请保留数据")
