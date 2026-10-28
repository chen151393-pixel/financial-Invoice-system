"""identity：飞书登录、部门与人员同步、角色（2026-10-27）。

人员与部门以飞书为准，本地只保存副本；部门默认角色与个人角色由管理员配置。
会话仍在 API 进程内存中（docs/feishu-identity-plan.md 第 1 期）。
"""

from alembic import op
from backend.core.schema import ID, TIMESTAMP, table_options, timestamps
from sqlalchemy import CHAR, JSON, Boolean, Column, Index, Integer, String, UniqueConstraint, text

revision = "0033_identity_directory"
down_revision = "0032_review_calculations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "identity_departments",
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
    op.create_table(
        "identity_sync_scopes",
        Column("id", ID, primary_key=True, autoincrement=True, comment="同步范围主键"),
        Column(
            "department_id",
            ID,
            nullable=False,
            comment="同步根部门，指向 identity_departments.id；含全部下级",
        ),
        Column("created_by", String(200), nullable=False, comment="设置该范围的认证操作者"),
        *timestamps(),
        UniqueConstraint("department_id", name="uq_identity_sync_scope"),
        comment="成员同步范围：只同步这些部门及其下级部门的成员，范围外的人不能登录",
        **table_options,
    )
    op.create_table(
        "identity_department_roles",
        Column("id", ID, primary_key=True, autoincrement=True, comment="部门默认角色主键"),
        Column("department_id", ID, nullable=False, comment="部门，指向 identity_departments.id"),
        Column("role", String(40), nullable=False, comment="角色代码，见 identity/policy/role_policy.py"),
        Column("granted_by", String(200), nullable=False, comment="授予该角色的认证操作者"),
        *timestamps(),
        UniqueConstraint("department_id", "role", name="uq_identity_department_role"),
        comment="部门默认角色：该部门及其下级部门的成员自动获得",
        **table_options,
    )
    op.create_table(
        "identity_users",
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
    op.create_table(
        "identity_user_departments",
        Column("id", ID, primary_key=True, autoincrement=True, comment="人员部门关系主键"),
        Column("user_id", ID, nullable=False, comment="人员，指向 identity_users.id"),
        Column("department_id", ID, nullable=False, comment="部门，指向 identity_departments.id"),
        *timestamps(),
        UniqueConstraint("user_id", "department_id", name="uq_identity_user_department"),
        comment="人员所属部门，以飞书为准；每次同步整体替换",
        **table_options,
    )
    op.create_table(
        "identity_user_roles",
        Column("id", ID, primary_key=True, autoincrement=True, comment="个人角色主键"),
        Column("user_id", ID, nullable=False, comment="人员，指向 identity_users.id"),
        Column("role", String(40), nullable=False, comment="角色代码，见 identity/policy/role_policy.py"),
        Column("granted_by", String(200), nullable=False, comment="授予该角色的认证操作者"),
        *timestamps(),
        UniqueConstraint("user_id", "role", name="uq_identity_user_role"),
        comment="管理员给个人追加的角色；人员 custom_roles 为是时只按这些角色授权",
        **table_options,
    )
    op.create_table(
        "identity_login_flows",
        Column("id", ID, primary_key=True, autoincrement=True, comment="登录流程主键"),
        Column("state_hash", CHAR(64), nullable=False, comment="state 的 SHA-256；原文只发给飞书，不入库"),
        Column(
            "browser_hash",
            CHAR(64),
            nullable=False,
            comment="登录流程 Cookie 的 SHA-256；回调时须一致，防止把他人的授权码登录到本浏览器",
        ),
        Column("return_to", String(500), nullable=False, comment="登录成功后回到的站内路径"),
        Column(
            "status",
            String(20),
            nullable=False,
            comment="pending 待回调；checking 正在向飞书核实；success 已登录；failed 失败",
        ),
        Column("reason", String(300), comment="失败原因，登录页展示"),
        Column("user_id", String(64), comment="完成登录的飞书 user_id"),
        Column("expires_at", TIMESTAMP, nullable=False, comment="state 过期时间，UTC；创建后 10 分钟"),
        Column("finished_at", TIMESTAMP, comment="回调处理完成时间，UTC"),
        *timestamps(),
        UniqueConstraint("state_hash", name="uq_identity_login_state"),
        comment="飞书登录流程：state 只能使用一次",
        **table_options,
    )
    op.create_table(
        "identity_sync_runs",
        Column("id", ID, primary_key=True, autoincrement=True, comment="同步记录主键"),
        Column("trigger", String(20), nullable=False, comment="manual 手动；schedule 定时"),
        Column("started_by", String(200), nullable=False, comment="发起的认证操作者；定时为 system"),
        Column("status", String(20), nullable=False, comment="running 进行中；succeeded 成功；failed 失败"),
        Column("departments", Integer, nullable=False, server_default=text("0"), comment="读取到的部门数"),
        Column("users_added", Integer, nullable=False, server_default=text("0"), comment="新增人员数"),
        Column(
            "users_updated",
            Integer,
            nullable=False,
            server_default=text("0"),
            comment="信息或部门有变化的人员数",
        ),
        Column(
            "users_deactivated",
            Integer,
            nullable=False,
            server_default=text("0"),
            comment="改为不可登录的人员数",
        ),
        Column("error", String(500), comment="失败原因；失败时不停用任何人员"),
        Column("started_at", TIMESTAMP, nullable=False, comment="开始时间，UTC"),
        Column("finished_at", TIMESTAMP, comment="结束时间，UTC"),
        *timestamps(),
        comment="飞书部门与成员同步记录",
        **table_options,
    )
    op.create_table(
        "identity_audit",
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


def downgrade():
    raise RuntimeError("人员、角色与审计记录可能已被使用，不能降级删除；请保留数据")
