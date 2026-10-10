"""独立保存报关关联依据和当前结果，并迁移旧报关JSON中的关系部分。"""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import mysql

revision = "0005_customs_relations"
down_revision = "0004_invoice_allocations"
branch_labels = None
depends_on = None

TABLE = "customs_reconciliation_results"
EVIDENCE = "JSON_EXTRACT(c.source_data, '$.relationEvidence')"


def field(path):
    return f"JSON_EXTRACT({EVIDENCE}, '$.{path}')"


def string(path):
    return f"NULLIF(JSON_UNQUOTE({field(path)}), 'null')"


def instant(path):
    value = string(path)
    return (
        f"CASE WHEN SUBSTRING({value},20,1)='.' THEN "
        f"STR_TO_DATE(SUBSTRING_INDEX(SUBSTRING_INDEX({value},'+',1),'Z',1), '%Y-%m-%dT%H:%i:%s.%f') "
        f"ELSE STR_TO_DATE(SUBSTRING({value},1,19), '%Y-%m-%dT%H:%i:%s') END"
    )


def upgrade():
    if not context.is_offline_mode():
        connection = op.get_bind()
        invalid = connection.execute(
            sa.text(f"""
            SELECT COUNT(*) FROM customs_declarations c
            WHERE JSON_CONTAINS_PATH(c.source_data,'one','$.relationEvidence') = 1
            AND (COALESCE(JSON_TYPE({EVIDENCE}),'') <> 'OBJECT'
              OR COALESCE({string("account")},'') <> c.ns_account
              OR COALESCE({string("declarationId")},'') <> c.ns_internal_id
              OR COALESCE({string("version")},'') <> '1'
              OR COALESCE({string("status")},'') NOT IN ('matched','partial','collected'))
        """)
        ).scalar_one()
        if invalid:
            raise RuntimeError("旧关系依据存在身份或版本不一致，未迁移；请先核实来源")
    scope = sa.String(100, collation="utf8mb4_bin")
    op.create_table(
        TABLE,
        sa.Column(
            "id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True, comment="本地结果主键"
        ),
        sa.Column("tenant_id", scope, nullable=False, comment="后端身份派生的数据归属"),
        sa.Column("ns_account", scope, nullable=False, comment="NS账套，与报关单一致"),
        sa.Column(
            "customs_declaration_id", mysql.BIGINT(unsigned=True), nullable=False, comment="报关单本地主键"
        ),
        sa.Column("evidence_version", sa.Integer(), nullable=False, comment="关联依据契约版本"),
        sa.Column(
            "status", sa.String(16), nullable=False, comment="partial待核实；collected仅依据；matched关联完整"
        ),
        sa.Column(
            "mode",
            sa.String(32),
            nullable=False,
            comment="full_sync完整同步；evidence_backfill补拉；dependency_changed失效",
        ),
        sa.Column("review_ready", sa.Boolean(), nullable=False, comment="业务依据是否完整，不表示审核通过"),
        sa.Column("reason", sa.Text(), nullable=False, comment="未满足完整性的原因"),
        sa.Column("issues", sa.JSON(), nullable=False, comment="具体来源问题列表"),
        sa.Column("raw_line_count", sa.Integer(), nullable=False, comment="原始报关行数"),
        sa.Column("packing_line_count", sa.Integer(), nullable=False, comment="Packing明细行数"),
        sa.Column("purchase_link_count", sa.Integer(), nullable=False, comment="销售至母采购行关系数"),
        sa.Column("parent_line_count", sa.Integer(), nullable=False, comment="母采购来源行数"),
        sa.Column("evidence_data", sa.JSON(), nullable=False, comment="原始行、Packing、母子采购身份等依据"),
        sa.Column("evidence_read_at", mysql.DATETIME(fsp=6), comment="依据读取时间UTC"),
        sa.Column("comparison_payload", sa.JSON(), comment="NS v3整单关联、数量、金额及币种的完整字符串快照"),
        sa.Column("comparison_digest", sa.String(64), comment="整单内容SHA256，用于判断旧审核是否适用"),
        sa.Column("query_request_id", sa.String(100), comment="NS关联查询编号"),
        sa.Column("query_completed_at", mysql.DATETIME(fsp=6), comment="NS关联查询完成时间UTC"),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False, comment="本地首次保存时间UTC"),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False, comment="本地最近更新时间UTC"),
        sa.UniqueConstraint(
            "tenant_id", "ns_account", "customs_declaration_id", name="uq_customs_reconciliation"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ns_account", "customs_declaration_id"],
            ["customs_declarations.tenant_id", "customs_declarations.ns_account", "customs_declarations.id"],
            name="fk_customs_reconciliation_parent",
        ),
        sa.CheckConstraint(
            "status IN ('partial','collected','matched')", name="ck_customs_reconciliation_status"
        ),
        sa.CheckConstraint(
            "review_ready = 0 OR (status = 'matched' AND comparison_payload IS NOT NULL AND comparison_digest IS NOT NULL)",
            name="ck_customs_reconciliation_ready",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_bin",
        comment="报关单关联依据和当前核对结果，一单一条；审核历史保存在应用库",
    )
    op.create_index(
        "ix_customs_reconciliation_status", TABLE, ["tenant_id", "ns_account", "status", "review_ready"]
    )
    payload = field("comparison.payload")
    has_payload = f"JSON_TYPE({payload}) = 'OBJECT'"
    op.execute(f"""
        INSERT INTO {TABLE} (
          tenant_id, ns_account, customs_declaration_id, evidence_version, status, mode, review_ready,
          reason, issues, raw_line_count, packing_line_count, purchase_link_count, parent_line_count,
          evidence_data, evidence_read_at, comparison_payload, comparison_digest, query_request_id,
          query_completed_at, created_at, updated_at)
        SELECT c.tenant_id, c.ns_account, c.id, 1, {string("status")},
          COALESCE({string("mode")},'full_sync'),
          CASE WHEN {string("status")} = 'matched' AND {string("comparison.ready")} = 'true' AND {has_payload} THEN 1 ELSE 0 END,
          COALESCE({string("comparison.reason")},'已迁移原有依据，具体问题见issues'),
          COALESCE({field("issues")},JSON_ARRAY()),
          COALESCE(JSON_LENGTH({field("rawLines")}),0), COALESCE(JSON_LENGTH({field("packingLines")}),0),
          COALESCE(JSON_LENGTH({field("purchaseLinks")}),0), COALESCE(JSON_LENGTH({field("parentLines")}),0),
          JSON_REMOVE({EVIDENCE}, '$.version','$.account','$.declarationId','$.readAt','$.status','$.mode','$.issues','$.comparison'),
          {instant("readAt")}, CASE WHEN {has_payload} THEN {payload} ELSE NULL END,
          {string("comparison.digest")}, {string("comparison.requestId")}, {instant("comparison.readCompletedAt")},
          UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)
        FROM customs_declarations c WHERE JSON_TYPE({EVIDENCE}) = 'OBJECT'
    """)
    # 成功复制后只移除旧关系键，原单头、明细及同步时间全部保持原值。
    op.execute(f"""
        UPDATE customs_declarations c JOIN {TABLE} r
          ON r.tenant_id=c.tenant_id AND r.ns_account=c.ns_account AND r.customs_declaration_id=c.id
        SET c.source_data=JSON_REMOVE(c.source_data,'$.relationEvidence')
        WHERE JSON_CONTAINS_PATH(c.source_data,'one','$.relationEvidence')=1
    """)


def downgrade():
    raise RuntimeError("关联结果包含业务依据，不自动删除或还原旧JSON，请先制定数据保留方案")
