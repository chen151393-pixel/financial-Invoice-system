"""飞书人员、所属部门与个人角色；人员以飞书为准，系统不维护本地账号档案。"""

from sqlalchemy import Boolean, Column, String, Table, UniqueConstraint, text

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

users = Table(
    "identity_users",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="人员本地主键"),
    Column(
        "user_id",
        String(64),
        nullable=False,
        comment="飞书企业内用户 ID（user_id）；操作者记为 user:fs:<user_id>",
    ),
    Column("open_id", String(64), comment="飞书应用内用户 ID（open_id）"),
    Column("union_id", String(64), comment="飞书开发者维度用户 ID（union_id）"),
    Column("name", String(200), nullable=False, comment="姓名，以飞书为准"),
    Column("avatar_url", String(1024), comment="头像地址（72×72）"),
    Column(
        "active",
        Boolean,
        nullable=False,
        server_default=text("1"),
        comment="是否可登录：在职、未冻结且在同步范围内；否时其会话立即失效",
    ),
    Column("inactive_reason", String(200), comment="不可登录的原因，例如已离职、已移出同步范围"),
    Column(
        "custom_roles",
        Boolean,
        nullable=False,
        server_default=text("0"),
        comment="是否只按个人角色授权；否时为部门默认角色与个人角色的并集",
    ),
    Column("synced_at", TIMESTAMP, nullable=False, comment="最近一次从飞书读到该人员的时间，UTC"),
    Column("last_login_at", TIMESTAMP, comment="最近一次飞书登录时间，UTC"),
    *timestamps(),
    UniqueConstraint("user_id", name="uq_identity_user_id"),
    comment="飞书人员副本：同步范围内的成员，登录时按此校验在职与角色",
    **table_options,
)

user_departments = Table(
    "identity_user_departments",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="人员部门关系主键"),
    Column("user_id", ID, nullable=False, comment="人员，指向 identity_users.id"),
    Column("department_id", ID, nullable=False, comment="部门，指向 identity_departments.id"),
    *timestamps(),
    UniqueConstraint("user_id", "department_id", name="uq_identity_user_department"),
    comment="人员所属部门，以飞书为准；每次同步整体替换",
    **table_options,
)

user_roles = Table(
    "identity_user_roles",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="个人角色主键"),
    Column("user_id", ID, nullable=False, comment="人员，指向 identity_users.id"),
    Column("role", String(40), nullable=False, comment="角色代码，见 identity/policy/role_policy.py"),
    Column("granted_by", String(200), nullable=False, comment="授予该角色的认证操作者"),
    *timestamps(),
    UniqueConstraint("user_id", "role", name="uq_identity_user_role"),
    comment="管理员给个人追加的角色；人员 custom_roles 为是时只按这些角色授权",
    **table_options,
)
