"""角色页面配置；空数组明确表示该角色没有可访问页面。"""

from sqlalchemy import JSON, Column, Integer, String, Table, UniqueConstraint

from backend.core.schema import ID, schema_metadata, table_options, timestamps

role_pages = Table(
    "identity_role_pages",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="角色页面配置主键"),
    Column("role", String(40), nullable=False, comment="固定角色代码；管理员页面权限不可修改"),
    Column("pages", JSON, nullable=False, comment="允许访问的页面代码数组；空数组为无权限"),
    Column("revision", Integer, nullable=False, comment="编辑版本；未配置时接口版本为 0"),
    Column("updated_by", String(200), nullable=False, comment="最近保存的认证管理员"),
    *timestamps(),
    UniqueConstraint("role", name="uq_identity_role_pages_role"),
    comment="角色的页面访问范围，多角色取并集，独立于具体业务操作权限",
    **table_options,
)
