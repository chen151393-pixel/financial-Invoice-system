"""报关关联当前结果；一张报关单一条记录，审批历史仍由财务模块保存。"""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql

RELATION_TABLE = "customs_reconciliation_results"


def define_relation_table(metadata):
    identity = Integer().with_variant(mysql.BIGINT(unsigned=True), "mysql")
    scope = String(100).with_variant(mysql.VARCHAR(100, collation="utf8mb4_bin"), "mysql")
    instant = DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
    return Table(
        RELATION_TABLE,
        metadata,
        Column("id", identity, primary_key=True, autoincrement=True),
        Column("tenant_id", scope, nullable=False),
        Column("ns_account", scope, nullable=False),
        Column("customs_declaration_id", identity, nullable=False),
        Column("evidence_version", Integer, nullable=False),
        Column("status", String(16), nullable=False),
        Column("mode", String(32), nullable=False),
        Column("review_ready", Boolean, nullable=False),
        Column("reason", Text, nullable=False),
        Column("issues", JSON, nullable=False),
        Column("raw_line_count", Integer, nullable=False),
        Column("packing_line_count", Integer, nullable=False),
        Column("purchase_link_count", Integer, nullable=False),
        Column("parent_line_count", Integer, nullable=False),
        Column("evidence_data", JSON, nullable=False),
        Column("evidence_read_at", instant),
        Column("comparison_payload", JSON(none_as_null=True)),
        Column("comparison_digest", String(64)),
        Column("query_request_id", String(100)),
        Column("query_completed_at", instant),
        Column("created_at", instant, nullable=False),
        Column("updated_at", instant, nullable=False),
        UniqueConstraint(
            "tenant_id", "ns_account", "customs_declaration_id", name="uq_customs_reconciliation"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "ns_account", "customs_declaration_id"],
            ["customs_declarations.tenant_id", "customs_declarations.ns_account", "customs_declarations.id"],
            name="fk_customs_reconciliation_parent",
        ),
        CheckConstraint(
            "status IN ('partial','collected','matched')", name="ck_customs_reconciliation_status"
        ),
        CheckConstraint(
            "review_ready = 0 OR (status = 'matched' AND comparison_payload IS NOT NULL AND comparison_digest IS NOT NULL)",
            name="ck_customs_reconciliation_ready",
        ),
        Index("ix_customs_reconciliation_status", "tenant_id", "ns_account", "status", "review_ready"),
    )
