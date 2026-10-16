"""task：外部群目录与导入预览；降级保留人工确认记录。"""

from alembic import op
from backend.core.schema import ID, TIMESTAMP, document, identifier, table_options, timestamps
from sqlalchemy import Column, Integer, String, UniqueConstraint

revision = "0017_task_external_groups"
down_revision = "0016_sync_lemon_bindings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_external_groups",
        Column("id", ID, primary_key=True, autoincrement=True, comment="外部群目录主键"),
        Column("chat_id", identifier(190), nullable=False, comment="企微外部群身份，区分大小写"),
        Column("group_name", String(200), nullable=False, comment="导入群名"),
        Column("owner_name", String(100), nullable=False, comment="导入群主姓名"),
        Column("owner_userid", identifier(190), nullable=False, comment="导入群主企微用户 ID"),
        Column("member_count", Integer, nullable=False, comment="导入时群人数"),
        Column("department", String(255), nullable=False, comment="导入群主所在部门"),
        Column("group_created_at", TIMESTAMP, nullable=False, comment="群创建时间，UTC"),
        Column("filename", String(255), nullable=False, comment="最近导入的文件名"),
        Column("version", Integer, nullable=False, comment="目录乐观版本"),
        Column("updated_by", String(200), nullable=False, comment="最后确认导入的认证身份"),
        *timestamps(),
        UniqueConstraint("chat_id", name="uq_task_external_group_chat"),
        comment="Excel 导入外部群目录，待人工维护供应商关联",
        **table_options,
    )
    op.create_table(
        "task_group_imports",
        Column("id", identifier(36), primary_key=True, comment="随机导入预览编号"),
        Column("owner", String(200), nullable=False, comment="创建预览的认证身份"),
        Column("filename", String(255), nullable=False, comment="原始文件名"),
        Column("status", String(20), nullable=False, comment="pending 或 confirmed"),
        Column("snapshot", document, nullable=False, comment="服务端解析的不可变行和候选快照 JSON"),
        Column("confirmation", document, nullable=True, comment="确认请求与真实结果 JSON，用于幂等重放"),
        *timestamps(),
        comment="外部群导入预览和确认留痕，不保存原始文件",
        **table_options,
    )


def downgrade():
    raise RuntimeError(
        "外部群目录和人工确认记录不可自动丢弃，请保留 task_external_groups 与 task_group_imports"
    )
