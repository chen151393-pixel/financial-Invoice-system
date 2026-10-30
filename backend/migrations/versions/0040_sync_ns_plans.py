"""sync：NS 来源定时同步计划；批次复用 sync_runs，分页执行记录复用 sync_ns_runs 并指向所属批次。

降级只在尚无计划、计划批次与计划分页记录时允许；已有数据会丢弃关联及待核实证据，拒绝降级。
"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP, identifier, table_options, timestamps

revision = "0040_sync_ns_plans"
down_revision = "0039_task_wecom_directory"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sync_ns_plans",
        sa.Column("id", ID, primary_key=True, autoincrement=True, comment="计划主键"),
        sa.Column("scope_key", identifier(64), nullable=False, comment="NS 账户摘要，每个账户一份计划"),
        sa.Column(
            "owner", identifier(190), nullable=False, comment="最近保存计划的管理员，后台执行沿用该身份"
        ),
        sa.Column("enabled", sa.Boolean, nullable=False, comment="是否启用"),
        sa.Column("revision", sa.Integer, nullable=False, comment="编辑版本，防止覆盖并发修改"),
        sa.Column("configuration", sa.JSON, nullable=False, comment="单据范围、每日时间和回扫天数，不含凭据"),
        sa.Column("next_run_at", TIMESTAMP, comment="下一次触发时间，UTC"),
        *timestamps(),
        sa.UniqueConstraint("scope_key", name="uq_sync_ns_plan_scope"),
        comment="NS 来源（报关单、子采购单）每日定时同步计划",
        **table_options,
    )
    # sync_runs.plan_id 的外键指向柠檬云计划，NS 批次另用 ns_plan_id，保留原字段含义。
    with op.batch_alter_table("sync_runs") as batch:
        batch.add_column(sa.Column("ns_plan_id", ID, comment="NS 来源计划；柠檬云批次使用 plan_id"))
        batch.create_foreign_key("fk_sync_run_ns_plan", "sync_ns_plans", ["ns_plan_id"], ["id"])
    with op.batch_alter_table("sync_ns_runs") as batch:
        batch.add_column(sa.Column("run_id", ID, comment="所属定时计划批次；手动按批保存为空"))
        batch.create_foreign_key("fk_sync_ns_run_batch", "sync_runs", ["run_id"], ["id"])
        batch.create_index("ix_sync_ns_run_batch", ["run_id", "status"])


def downgrade():
    if not op.get_context().as_sql:
        bind = op.get_bind()
        used = (
            "SELECT 1 FROM sync_ns_plans",
            "SELECT 1 FROM sync_runs WHERE ns_plan_id IS NOT NULL",
            "SELECT 1 FROM sync_ns_runs WHERE run_id IS NOT NULL",
        )
        if any(bind.execute(sa.text(query)).first() for query in used):
            raise RuntimeError("NS 计划批次及分页记录可能含待核实结果，不能降级删除；请保留数据")
    with op.batch_alter_table("sync_ns_runs") as batch:
        batch.drop_index("ix_sync_ns_run_batch")
        batch.drop_constraint("fk_sync_ns_run_batch", type_="foreignkey")
        batch.drop_column("run_id")
    with op.batch_alter_table("sync_runs") as batch:
        batch.drop_constraint("fk_sync_run_ns_plan", type_="foreignkey")
        batch.drop_column("ns_plan_id")
    op.drop_table("sync_ns_plans")
