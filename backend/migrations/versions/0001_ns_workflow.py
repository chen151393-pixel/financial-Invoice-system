"""Persistent NS previews, target locks and audit; MySQL 8.0 and SQLite."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT, VARCHAR

revision = "0001_ns_workflow"
down_revision = None
branch_labels = None
depends_on = None


def key(length):
    return sa.String(length).with_variant(VARCHAR(length, collation="utf8mb4_bin"), "mysql")


def upgrade():
    document = sa.Text().with_variant(LONGTEXT(), "mysql")
    options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}
    op.create_table(
        "ns_previews",
        sa.Column("id", key(36), primary_key=True),
        sa.Column("account", key(100), nullable=False),
        sa.Column("owner", key(200), nullable=False),
        sa.Column("target", key(255), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("payload", document, nullable=False),
        sa.Column("snapshot", document),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("expires", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("result", document),
        **options,
    )
    op.create_index("ix_ns_previews_owner_created", "ns_previews", ["owner", "created_at"])
    op.create_table(
        "ns_target_locks",
        sa.Column("account", key(100), primary_key=True),
        sa.Column("target", key(255), primary_key=True),
        sa.Column("preview_id", key(36), sa.ForeignKey("ns_previews.id"), nullable=False, unique=True),
        **options,
    )
    op.create_table(
        "ns_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("at", sa.BigInteger(), nullable=False),
        sa.Column("actor", key(200), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("preview_id", key(36), sa.ForeignKey("ns_previews.id"), nullable=False),
        **options,
    )


def downgrade():
    op.drop_table("ns_audit")
    op.drop_table("ns_target_locks")
    op.drop_table("ns_previews")
