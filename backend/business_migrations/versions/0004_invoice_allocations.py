"""增加人工确认的发票采购行分配，不修改来源表。"""

import sqlalchemy as sa
from alembic import op

revision = "0004_invoice_allocations"
down_revision = "0003_customs_price_precision"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "invoice_purchase_allocations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, comment="认证身份派生的数据范围"),
        sa.Column("request_id", sa.String(36), nullable=False, comment="确认请求幂等键"),
        sa.Column("request_hash", sa.String(64), nullable=False, comment="确认请求内容摘要"),
        sa.Column("invoice_id", sa.String(20), nullable=False, comment="本地发票主键"),
        sa.Column("invoice_line_id", sa.String(20), nullable=False, comment="本地发票行主键"),
        sa.Column("purchase_line_id", sa.String(20), nullable=False, comment="本地子采购行主键"),
        sa.Column("quantity", sa.Numeric(26, 8), nullable=False, comment="本次分配数量"),
        sa.Column("gross", sa.Numeric(26, 8), nullable=False, comment="本次分配含税金额"),
        sa.Column("source_hash", sa.String(64), nullable=False, comment="确认时来源快照摘要"),
        sa.Column("purchase_hash", sa.String(64), nullable=False, comment="采购行及单头业务快照摘要"),
        sa.Column(
            "source_snapshot", sa.JSON(), nullable=False, comment="确认时两侧行及校验依据，不随来源更新"
        ),
        sa.Column("actor", sa.String(255), nullable=False, comment="认证操作者"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="确认时间UTC"),
        sa.UniqueConstraint("tenant_id", "request_id", name="uq_matching_request"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        comment="发票与子采购行人工分配，仅本地保存不写NS",
    )


def downgrade():
    raise RuntimeError("分配含业务确认记录，不自动删除；请先制定数据保留方案")
