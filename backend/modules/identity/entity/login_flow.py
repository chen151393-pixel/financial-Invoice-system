"""飞书登录流程：一次性 state 与回跳地址，失败原因留给登录页读取。"""

from sqlalchemy import CHAR, Column, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

login_flows = Table(
    "identity_login_flows",
    schema_metadata,
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
