"""settlement：香港到账银行水单原件。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, identifier, table_options, timestamps

revision = "0054_settlement_hk_slips"
down_revision = "0053_settlement_group_merge"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "settlement_hk_slips",
        sa.Column(
            "batch_id",
            ID,
            sa.ForeignKey("settlement_batches.id"),
            primary_key=True,
            autoincrement=False,
            comment="所属香港批次主键，一批次一份水单",
        ),
        sa.Column("file_name", sa.String(255), nullable=False, comment="银行水单原始文件名"),
        sa.Column("file_id", identifier(36), nullable=False, comment="资料目录内服务端生成的 PDF 文件标识"),
        sa.Column("sha256", identifier(64), nullable=False, comment="原件 SHA-256 校验值"),
        sa.Column("uploaded_by", sa.String(190), nullable=False, comment="登记操作人，来自认证身份"),
        *timestamps(),
        comment="香港到账银行水单原件，随批次留存不写 NS",
        **table_options,
    )


def downgrade():
    if (
        not op.get_context().as_sql
        and op.get_bind().execute(sa.text("SELECT 1 FROM settlement_hk_slips LIMIT 1")).first()
    ):
        raise RuntimeError("已有香港银行水单原件记录，拒绝回退")
    op.drop_table("settlement_hk_slips")
