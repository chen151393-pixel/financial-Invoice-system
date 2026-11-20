"""settlement：单票资料组合并的后继关系与原始范围，不删除旧组或文件。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP

revision = "0053_settlement_group_merge"
down_revision = "0052_settlement_group_comments"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("settlement_document_groups") as batch:
        batch.add_column(
            sa.Column("initial_declaration_nos", sa.JSON, comment="创建时成员快照，合并后仍保留原始范围")
        )
        batch.add_column(sa.Column("merged_into_id", ID, comment="合并后的新资料组，原组保留供追溯"))
        batch.add_column(sa.Column("merged_at", TIMESTAMP, comment="合并时间，UTC"))
        batch.add_column(sa.Column("merged_by", sa.String(190), comment="合并操作人，取认证身份"))
        batch.create_foreign_key(
            "fk_settlement_document_group_successor", "settlement_document_groups", ["merged_into_id"], ["id"]
        )


def downgrade():
    if (
        not op.get_context().as_sql
        and op.get_bind()
        .execute(sa.text("SELECT 1 FROM settlement_document_groups WHERE merged_into_id IS NOT NULL LIMIT 1"))
        .first()
    ):
        raise RuntimeError("已有资料组合并记录，拒绝回退并丢失后继关系")
    with op.batch_alter_table("settlement_document_groups") as batch:
        batch.drop_constraint("fk_settlement_document_group_successor", type_="foreignkey")
        for name in ("merged_by", "merged_at", "merged_into_id", "initial_declaration_nos"):
            batch.drop_column(name)
