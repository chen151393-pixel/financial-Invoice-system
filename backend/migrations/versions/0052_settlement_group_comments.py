"""settlement：补齐资料组中文备注；只改元数据，保留既有资料。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, TIMESTAMP, identifier

revision = "0052_settlement_group_comments"
down_revision = "0051_settlement_document_groups"
branch_labels = None
depends_on = None

GROUPS = {
    "settlement_document_groups": (
        "直接收汇资料组，同收货人同币种，可含不同申报抬头",
        [
            ("id", ID, "本地自增主键"),
            ("group_no", identifier(40), "资料组编号"),
            ("request_id", identifier(36), "创建幂等请求标识"),
            ("consignee", sa.String(200), "创建时境外收货人"),
            ("currency", sa.String(10), "创建时币种，不跨币种合并"),
            ("created_by", sa.String(190), "创建人，取认证身份"),
            ("created_at", TIMESTAMP, "本地记录创建时间，UTC"),
            ("updated_at", TIMESTAMP, "本地记录最后更新时间，UTC；由 DAO 更新"),
        ],
    ),
    "settlement_document_group_items": (
        "直接收汇资料组成员，一张报关单只属于一组",
        [
            ("id", ID, "本地自增主键"),
            ("group_id", ID, "所属直接收汇资料组"),
            ("declaration_no", identifier(150), "资料组内报关单，一票只能属于一组"),
            ("created_at", TIMESTAMP, "成员归组时间，UTC"),
        ],
    ),
}


def _apply(clear):
    if op.get_context().dialect.name != "mysql":
        return
    for table, (comment, columns) in GROUPS.items():
        if clear:
            op.drop_table_comment(table, existing_comment=comment)
        else:
            op.create_table_comment(table, comment, existing_comment=None)
        for name, type_, description in columns:
            op.alter_column(
                table,
                name,
                existing_type=type_,
                existing_nullable=False,
                autoincrement=(name == "id"),
                comment=None if clear else description,
            )
    op.alter_column(
        "settlement_contracts",
        "document_key",
        existing_type=identifier(64),
        existing_nullable=True,
        comment=None if clear else "资料组内申报抬头与出口合同号的稳定标识",
    )


def upgrade():
    _apply(False)


def downgrade():
    _apply(True)
