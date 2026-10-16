"""人工确认导入的外部群目录，不代表企微实时核验结果。"""

from sqlalchemy import Column, Integer, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, identifier, schema_metadata, table_options, timestamps

external_groups = Table(
    "task_external_groups",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="外部群目录主键"),
    Column("chat_id", identifier(190), nullable=False, comment="企微外部群身份，区分大小写"),
    Column("group_name", String(200), nullable=False, comment="导入群名"),
    Column("owner_name", String(100), nullable=False, comment="导入群主姓名"),
    Column("owner_userid", identifier(190), nullable=False, comment="导入群主企微用户 ID"),
    Column("member_count", Integer, nullable=True, comment="导入时群人数"),
    Column("department", String(255), nullable=False, comment="导入群主所在部门"),
    Column("group_created_at", TIMESTAMP, nullable=True, comment="群创建时间，UTC"),
    Column("filename", String(255), nullable=False, comment="最近导入的文件名"),
    Column("version", Integer, nullable=False, comment="目录乐观版本"),
    Column("updated_by", String(200), nullable=False, comment="最后确认导入的认证身份"),
    *timestamps(),
    UniqueConstraint("chat_id", name="uq_task_external_group_chat"),
    comment="Excel 导入外部群目录，待人工维护供应商关联",
    **table_options,
)
