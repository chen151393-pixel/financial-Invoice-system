"""持久化外部群导入预览及确认结果，刷新和重试不重复写入。"""

from sqlalchemy import Column, String, Table

from backend.core.schema import document, identifier, schema_metadata, table_options, timestamps

group_imports = Table(
    "task_group_imports",
    schema_metadata,
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
