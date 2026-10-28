"""飞书部门与成员同步记录。"""

from sqlalchemy import Column, Integer, String, Table, text

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

sync_runs = Table(
    "identity_sync_runs",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="同步记录主键"),
    Column("trigger", String(20), nullable=False, comment="manual 手动；schedule 定时"),
    Column("started_by", String(200), nullable=False, comment="发起的认证操作者；定时为 system"),
    Column("status", String(20), nullable=False, comment="running 进行中；succeeded 成功；failed 失败"),
    Column("departments", Integer, nullable=False, server_default=text("0"), comment="读取到的部门数"),
    Column("users_added", Integer, nullable=False, server_default=text("0"), comment="新增人员数"),
    Column(
        "users_updated", Integer, nullable=False, server_default=text("0"), comment="信息或部门有变化的人员数"
    ),
    Column(
        "users_deactivated", Integer, nullable=False, server_default=text("0"), comment="改为不可登录的人员数"
    ),
    Column("error", String(500), comment="失败原因；失败时不停用任何人员"),
    Column("started_at", TIMESTAMP, nullable=False, comment="开始时间，UTC"),
    Column("finished_at", TIMESTAMP, comment="结束时间，UTC"),
    *timestamps(),
    comment="飞书部门与成员同步记录",
    **table_options,
)
