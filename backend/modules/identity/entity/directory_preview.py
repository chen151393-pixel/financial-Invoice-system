"""短期组织预览与单独人员同步范围；预览不创建平台账号。"""

from sqlalchemy import JSON, Column, String, Table

from backend.core.schema import TIMESTAMP, schema_metadata, table_options, timestamps

directory_previews = Table(
    "identity_directory_previews",
    schema_metadata,
    Column("id", String(64), primary_key=True, comment="随机预览标识"),
    Column("actor", String(200), nullable=False, comment="创建预览的管理员"),
    Column("version", String(64), nullable=False, comment="读取前权限数据摘要，确认时复核"),
    Column("payload", JSON, nullable=False, comment="飞书部门与成员快照，过期清除"),
    Column("expires_at", TIMESTAMP, nullable=False, comment="预览过期时间，UTC"),
    Column("result", JSON, comment="已确认的范围与结果，用于幂等重试"),
    *timestamps(),
    comment="短期飞书组织预览；有效期十分钟",
    **table_options,
)

user_sync_scopes = Table(
    "identity_user_sync_scopes",
    schema_metadata,
    Column("user_id", String(64), primary_key=True, comment="单独选择的飞书 user_id"),
    Column("created_by", String(200), nullable=False, comment="设置范围的认证操作者"),
    *timestamps(),
    comment="个人同步范围，与部门范围取并集",
    **table_options,
)
