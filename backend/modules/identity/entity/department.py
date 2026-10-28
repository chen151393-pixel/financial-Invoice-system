"""飞书部门、同步范围与部门默认角色；部门以飞书为准，本地只保存副本。"""

from sqlalchemy import Boolean, Column, Index, String, Table, UniqueConstraint, text

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

departments = Table(
    "identity_departments",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="部门本地主键"),
    Column(
        "open_department_id",
        String(64),
        nullable=False,
        comment="飞书部门 ID（open_department_id，od- 开头）",
    ),
    Column("parent_open_id", String(64), comment="上级飞书部门 ID；0 表示企业根部门，空表示未知"),
    Column("name", String(200), nullable=False, comment="部门名称，以飞书为准"),
    Column(
        "active",
        Boolean,
        nullable=False,
        server_default=text("1"),
        comment="是否仍在飞书通讯录权限范围内且未删除；否时不再同步成员",
    ),
    Column("synced_at", TIMESTAMP, nullable=False, comment="最近一次从飞书读到该部门的时间，UTC"),
    *timestamps(),
    UniqueConstraint("open_department_id", name="uq_identity_department_open"),
    Index("ix_identity_department_parent", "parent_open_id"),
    comment="飞书部门副本，用于选择同步范围与配置部门默认角色",
    **table_options,
)

sync_scopes = Table(
    "identity_sync_scopes",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="同步范围主键"),
    Column(
        "department_id", ID, nullable=False, comment="同步根部门，指向 identity_departments.id；含全部下级"
    ),
    Column("created_by", String(200), nullable=False, comment="设置该范围的认证操作者"),
    *timestamps(),
    UniqueConstraint("department_id", name="uq_identity_sync_scope"),
    comment="成员同步范围：只同步这些部门及其下级部门的成员，范围外的人不能登录",
    **table_options,
)

department_roles = Table(
    "identity_department_roles",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="部门默认角色主键"),
    Column("department_id", ID, nullable=False, comment="部门，指向 identity_departments.id"),
    Column("role", String(40), nullable=False, comment="角色代码，见 identity/policy/role_policy.py"),
    Column("granted_by", String(200), nullable=False, comment="授予该角色的认证操作者"),
    *timestamps(),
    UniqueConstraint("department_id", "role", name="uq_identity_department_role"),
    comment="部门默认角色：该部门及其下级部门的成员自动获得",
    **table_options,
)
