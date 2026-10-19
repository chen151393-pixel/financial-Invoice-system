"""每个管理员绑定范围一份每日同步计划；时间存 UTC，配置时间按北京时间解释。"""

from sqlalchemy import JSON, Boolean, Column, Integer, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, identifier, schema_metadata, table_options, timestamps

lemon_plans = Table(
    "sync_lemon_plans",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="计划主键"),
    Column("scope_key", identifier(64), nullable=False, comment="应用、环境与管理员身份摘要"),
    Column("owner", identifier(190), nullable=False, comment="计划授权身份"),
    Column("enabled", Boolean, nullable=False, comment="是否启用"),
    Column("revision", Integer, nullable=False, comment="编辑版本，防止覆盖并发修改"),
    Column("configuration", JSON, nullable=False, comment="账套范围、每日时间和滚动天数快照，不含凭据"),
    Column("next_run_at", TIMESTAMP, comment="下一次触发时间，UTC"),
    *timestamps(),
    UniqueConstraint("scope_key", name="uq_sync_lemon_plan_scope"),
    comment="柠檬云每日同步计划",
    **table_options,
)
