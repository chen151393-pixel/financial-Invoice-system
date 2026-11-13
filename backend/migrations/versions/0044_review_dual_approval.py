"""海关审核记录与财务审核放行依据：新增一张表、一个可空字段。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP, table_options, timestamps
from sqlalchemy import CHAR, Column, ForeignKey, Integer, MetaData, String, Table, UniqueConstraint

revision = "0044_review_dual_approval"
down_revision = "0043_task_supplier_owners"
branch_labels = None
depends_on = None
metadata = MetaData()
# 回执表仅用于解析外键；财务审核表只新增放行字段，不重写已有审核内容。
Table("review_customs_receipts", metadata, Column("id", ID, primary_key=True))

customs_approvals = Table(
    "review_customs_approvals",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="本地自增主键"),
    Column("receipt_id", ID, ForeignKey("review_customs_receipts.id"), nullable=False, comment="海关回执 ID"),
    Column("receipt_revision", Integer, nullable=False, comment="审核时回执版本"),
    Column("receipt_sha256", CHAR(64), nullable=False, comment="审核时回执内容摘要"),
    Column("customs_declaration_id", ID, nullable=False, comment="来源报关单 ID，跨模块不建外键"),
    Column("source_sha256", CHAR(64), nullable=False, comment="审核时 NS 来源摘要"),
    Column("method", String(20), nullable=False, comment="auto 自动审核；manual 人工审核"),
    Column("approved_by", String(190), nullable=False, comment="审核人认证身份"),
    Column("approved_at", TIMESTAMP, nullable=False, comment="审核通过时间，UTC"),
    Column("note", String(300), comment="人工审核说明"),
    *timestamps(),
    UniqueConstraint(
        "receipt_id",
        "receipt_revision",
        "customs_declaration_id",
        "source_sha256",
        name="uq_review_customs_approval_version",
    ),
    comment="海关审核不可变版本",
    **table_options,
)


def upgrade():
    customs_approvals.create(op.get_bind())
    op.add_column(
        "review_records",
        Column("customs_approval_id", ID, comment="双审核放行采用的海关审核 ID；空表示尚未放行，只设置一次"),
    )


def downgrade():
    connection = op.get_bind()
    released = sa.table("review_records", sa.column("customs_approval_id", ID))
    has_approval = connection.execute(sa.select(customs_approvals.c.id).limit(1)).first()
    has_release = connection.execute(
        sa.select(released.c.customs_approval_id).where(released.c.customs_approval_id.is_not(None)).limit(1)
    ).first()
    if has_approval or has_release:
        raise RuntimeError("海关审核或放行依据已有数据，禁止降级删除")
    op.drop_column("review_records", "customs_approval_id")
    customs_approvals.drop(connection)
