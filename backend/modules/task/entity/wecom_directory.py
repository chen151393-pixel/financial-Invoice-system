"""企微只读目录与同步状态；按企业及凭证摘要隔离，不存凭证或群成员清单。"""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, identifier, schema_metadata, table_options, timestamps

directories = Table(
    "task_wecom_directories",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="企微目录主键"),
    Column("scope", identifier(64), nullable=False, unique=True, comment="企业和凭证的 SHA256 范围摘要"),
    Column("status", String(20), nullable=False, comment="同步状态：queued/listing/details/ready/failed"),
    Column("run_token", identifier(36), nullable=True, comment="当前同步执行标识，防止失锁旧任务覆盖新进度"),
    Column("has_snapshot", Boolean, nullable=False, comment="是否有可使用的完整快照"),
    Column("discovered", Integer, nullable=False, comment="本次已发现的群数"),
    Column("completed", Integer, nullable=False, comment="本次已完成详情查询的群数，含不可访问群"),
    Column("total", Integer, nullable=True, comment="本次群总数；列表分页结束前未知"),
    Column("unavailable_count", Integer, nullable=False, comment="上次完整目录中不可访问的群数"),
    Column("synced_at", TIMESTAMP, nullable=True, comment="上次完整成功同步时间，UTC"),
    Column("next_sync_at", TIMESTAMP, nullable=False, comment="下次后台同步时间或失败冷却截止时间"),
    Column("error", String(500), nullable=False, comment="脱敏后的同步错误"),
    *timestamps(),
    comment="企微群目录同步状态与持久队列，每个凭证范围一条",
    **table_options,
)

groups = Table(
    "task_wecom_directory_groups",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="目录群主键"),
    Column("directory_id", ID, ForeignKey("task_wecom_directories.id"), nullable=False, comment="所属目录"),
    Column("chat_id", identifier(190), nullable=False, comment="企微群 ID"),
    Column("group_name", String(200), nullable=False, comment="企微返回的群名"),
    Column("owner_name", String(200), nullable=False, comment="企微返回的群主姓名"),
    Column("owner_userid", identifier(190), nullable=False, comment="企微群主 ID"),
    Column("member_count", Integer, nullable=False, comment="群人数，不存成员清单"),
    Column("group_created_at", TIMESTAMP, nullable=True, comment="企微群创建时间，UTC"),
    Column("is_active", Boolean, nullable=False, comment="是否在最近完整可见目录中"),
    *timestamps(),
    UniqueConstraint("directory_id", "chat_id", name="uq_task_wecom_directory_chat"),
    comment="企微群识别快照，与 Excel 导入目录分开保存",
    **table_options,
)
