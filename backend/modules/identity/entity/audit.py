"""身份审计：登录、同步范围与角色变更。"""

from sqlalchemy import JSON, Column, Index, String, Table

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options

audit = Table(
    "identity_audit",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="审计主键"),
    Column("actor", String(200), nullable=False, comment="操作者；登录失败时为飞书 user_id 或 anonymous"),
    Column(
        "action",
        String(40),
        nullable=False,
        comment="login 登录成功；login_failed 登录失败；scope 同步范围；department_roles 部门角色；user_roles 个人角色",
    ),
    Column("target", String(200), comment="操作对象，例如部门或人员本地 ID"),
    Column("detail", JSON, comment="变更前后或失败原因"),
    Column("created_at", TIMESTAMP, nullable=False, comment="发生时间，UTC"),
    Index("ix_identity_audit_created", "created_at"),
    comment="身份与权限审计记录，只追加",
    **table_options,
)
