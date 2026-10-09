"""应用库新增财务审核快照、状态和审计；不改业务来源八表。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT, VARCHAR

revision = "0002_finance_review"
down_revision = "0001_ns_workflow"
branch_labels = None
depends_on = None


def upgrade():
    def key(length):
        return sa.String(length).with_variant(VARCHAR(length, collation="utf8mb4_bin"), "mysql")

    options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}
    op.create_table(
        "finance_review_snapshots",
        sa.Column("id", key(36), primary_key=True),
        sa.Column("owner", key(200), nullable=False),
        sa.Column("account", key(100), nullable=False),
        sa.Column("declaration_id", key(190), nullable=False),
        sa.Column("digest", key(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text().with_variant(LONGTEXT(), "mysql"), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        **options,
    )
    op.create_index("ix_finance_snapshot_owner_created", "finance_review_snapshots", ["owner", "created_at"])
    op.create_table(
        "finance_reviews",
        sa.Column("owner", key(200), primary_key=True),
        sa.Column("account", key(100), primary_key=True),
        sa.Column("declaration_id", key(190), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", key(36), sa.ForeignKey("finance_review_snapshots.id")),
        sa.Column("digest", key(64)),
        sa.Column("reviewed_at", sa.BigInteger()),
        sa.Column("reviewed_by", key(200)),
        sa.Column("note", sa.String(300)),
        **options,
    )
    op.create_table(
        "finance_review_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("at", sa.BigInteger(), nullable=False),
        sa.Column("actor", key(200), nullable=False),
        sa.Column(
            "snapshot_id", key(36), sa.ForeignKey("finance_review_snapshots.id"), nullable=False, unique=True
        ),
        sa.Column("note", sa.String(300), nullable=False),
        **options,
    )


def downgrade():
    raise RuntimeError("财务审核包含不可丢弃的历史，请通过后续增量迁移调整")
