"""同步计划与持久任务队列。降级会丢弃待核实证据，明确禁止破坏性降级。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP, identifier, table_options, timestamps

revision = "0023_sync_background"
down_revision = "0022_task_notifications"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sync_lemon_plans",
        sa.Column("id", ID, primary_key=True, autoincrement=True, comment="计划主键"),
        sa.Column("scope_key", identifier(64), nullable=False, comment="应用、环境与管理员身份摘要"),
        sa.Column("owner", identifier(190), nullable=False, comment="计划授权身份"),
        sa.Column("enabled", sa.Boolean, nullable=False, comment="是否启用"),
        sa.Column("revision", sa.Integer, nullable=False, comment="编辑版本，防止覆盖并发修改"),
        sa.Column(
            "configuration", sa.JSON, nullable=False, comment="账套范围、每日时间和滚动天数快照，不含凭据"
        ),
        sa.Column("next_run_at", TIMESTAMP, comment="下一次触发时间，UTC"),
        *timestamps(),
        sa.UniqueConstraint("scope_key", name="uq_sync_lemon_plan_scope"),
        comment="柠檬云每日同步计划",
        **table_options,
    )
    # 旧记录与所有旧表数据保留；新字段仅由后台队列写入。
    with op.batch_alter_table("sync_runs") as batch:
        batch.add_column(sa.Column("scope_key", identifier(64), comment="后台任务身份范围"))
        batch.add_column(sa.Column("request_id", identifier(36), comment="幂等提交编号"))
        batch.add_column(sa.Column("plan_id", ID, comment="来源计划"))
        batch.add_column(sa.Column("phase", identifier(20), comment="后台任务阶段"))
        batch.add_column(sa.Column("configuration", sa.JSON, comment="不可变执行条件及授权绑定摘要"))
        batch.create_foreign_key("fk_sync_run_plan", "sync_lemon_plans", ["plan_id"], ["id"])
        batch.create_unique_constraint("uq_sync_run_request", ["scope_key", "request_id"])
        batch.create_index("ix_sync_run_scope_phase", ["scope_key", "phase"])
    create_jobs()
    op.add_column(
        "sync_lemon_runs",
        sa.Column(
            "background", sa.Boolean, nullable=False, server_default=sa.false(), comment="是否由后台队列执行"
        ),
    )


def create_jobs():
    op.create_table(
        "sync_lemon_jobs",
        sa.Column("id", ID, primary_key=True, autoincrement=True, comment="分片主键"),
        sa.Column("run_id", ID, nullable=False, comment="所属批次"),
        sa.Column(
            "request_id", identifier(36), nullable=False, comment="对应 sync_lemon_runs 的原子请求编号"
        ),
        sa.Column("asid", identifier(32), nullable=False, comment="授权账套编号"),
        sa.Column("account_name", sa.String(255), nullable=False, comment="发现时的账套名称"),
        sa.Column("start_date", sa.Date, nullable=False, comment="起始开票日期"),
        sa.Column("end_date", sa.Date, nullable=False, comment="结束开票日期"),
        sa.Column(
            "status",
            identifier(20),
            nullable=False,
            comment="分片状态：queued/running/completed/failed/unknown/split",
        ),
        sa.Column("error", sa.String(500), comment="脱敏原因"),
        *timestamps(),
        sa.ForeignKeyConstraint(["run_id"], ["sync_runs.id"], name="fk_sync_lemon_job_run"),
        sa.UniqueConstraint("request_id", name="uq_sync_lemon_job_request"),
        comment="柠檬云后台账套拉取分片",
        **table_options,
    )
    op.create_index("ix_sync_lemon_job_run", "sync_lemon_jobs", ["run_id", "status"])


def downgrade():
    raise RuntimeError("后台队列可能包含执行中或待核实结果，不能降级删除证据")
