"""settlement：资料组人工更新来源的前后依据和操作者留痕。"""

import sqlalchemy as sa
from alembic import op

revision = "0055_settlement_group_basis"
down_revision = "0054_settlement_hk_slips"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "settlement_document_groups",
        sa.Column(
            "basis_history", sa.JSON(), nullable=True, comment="人工确认更新来源的前后依据、时间和认证操作者"
        ),
    )


def downgrade():
    if (
        not op.get_context().as_sql
        and op.get_bind()
        .execute(sa.text("SELECT 1 FROM settlement_document_groups WHERE basis_history IS NOT NULL LIMIT 1"))
        .first()
    ):
        raise RuntimeError("已有资料组来源更新记录，拒绝丢失审计历史")
    op.drop_column("settlement_document_groups", "basis_history")
