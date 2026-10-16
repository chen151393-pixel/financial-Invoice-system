"""sync：持久保存账套选择与手动拉票结果；保留运行中记录，不能降级丢弃证据。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, identifier, table_options, timestamps

revision = "0018_sync_lemon_runs"
down_revision = "0017_task_external_groups"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sync_lemon_bindings",
        sa.Column("selected_asid", identifier(32), nullable=True, comment="已选择并核实可访问的账套编号"),
    )
    op.add_column(
        "sync_lemon_bindings",
        sa.Column("selected_name", identifier(255), nullable=True, comment="已选择账套名称"),
    )
    op.create_table(
        "sync_lemon_runs",
        sa.Column("id", ID, primary_key=True, autoincrement=True, comment="同步记录主键"),
        sa.Column("scope_key", identifier(64), nullable=False, comment="环境、应用与认证身份摘要"),
        sa.Column(
            "request_id", identifier(36), nullable=False, comment="调用方请求编号，重复提交只查询原结果"
        ),
        sa.Column("asid", identifier(32), nullable=False, comment="本次授权账套编号"),
        sa.Column("account_name", sa.String(255), nullable=False, comment="本次授权账套名称快照"),
        sa.Column("start_date", sa.Date, nullable=False, comment="起始开票日期"),
        sa.Column("end_date", sa.Date, nullable=False, comment="结束开票日期"),
        sa.Column(
            "status",
            identifier(20),
            nullable=False,
            comment="running执行中或待核实；completed已提交；failed未保存",
        ),
        sa.Column("result", sa.JSON, nullable=True, comment="已提交的实际保存统计"),
        sa.Column("error", sa.String(500), nullable=True, comment="脱敏失败原因"),
        *timestamps(),
        sa.UniqueConstraint("scope_key", "request_id", name="uq_sync_lemon_request"),
        comment="柠檬云手动拉票记录与结果，不保存令牌",
        **table_options,
    )
    op.create_index("ix_sync_lemon_scope_status", "sync_lemon_runs", ["scope_key", "status"])


def downgrade():
    raise RuntimeError("同步记录可能含执行中或未知结果，不能降级删除；请保留数据")
