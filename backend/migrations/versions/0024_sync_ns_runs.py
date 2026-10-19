"""sync：NS 来源按批后台保存的持久请求与结果；保留执行中/待核实记录，不能降级丢弃。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, identifier, table_options, timestamps

revision = "0024_sync_ns_runs"
down_revision = "0023_sync_background"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sync_ns_runs",
        sa.Column("id", ID, primary_key=True, autoincrement=True, comment="同步批次记录主键"),
        sa.Column("scope_key", identifier(64), nullable=False, comment="NS 账户与认证身份摘要"),
        sa.Column(
            "request_id", identifier(36), nullable=False, comment="调用方请求编号，重复提交只查询原结果"
        ),
        sa.Column(
            "kind", identifier(32), nullable=False, comment="sub-purchase-orders 或 customs-declarations"
        ),
        sa.Column("request", sa.JSON, nullable=False, comment="本批分页与日期条件快照"),
        sa.Column(
            "status",
            identifier(20),
            nullable=False,
            comment="running执行中或待核实；completed/partial/interrupted见逐单结果；failed未写入；unknown待核实",
        ),
        sa.Column("result", sa.JSON, nullable=True, comment="本批实际保存结果，含逐单状态"),
        sa.Column("error", sa.String(500), nullable=True, comment="脱敏失败原因"),
        *timestamps(),
        sa.UniqueConstraint("scope_key", "request_id", name="uq_sync_ns_request"),
        comment="NS 来源按批后台保存记录与结果，不保存令牌",
        **table_options,
    )
    op.create_index("ix_sync_ns_scope_status", "sync_ns_runs", ["scope_key", "status"])


def downgrade():
    raise RuntimeError("同步记录可能含执行中或待核实结果，不能降级删除；请保留数据")
