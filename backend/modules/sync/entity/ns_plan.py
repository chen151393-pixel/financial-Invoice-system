"""每个 NS 账户一份来源定时同步计划；时间存 UTC，配置时间按北京时间解释。"""

from sqlalchemy import JSON, Boolean, Column, Integer, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, identifier, schema_metadata, table_options, timestamps

ns_plans = Table(
    "sync_ns_plans",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="计划主键"),
    Column("scope_key", identifier(64), nullable=False, comment="NS 账户摘要，每个账户一份计划"),
    Column("owner", identifier(190), nullable=False, comment="最近保存计划的管理员，后台执行沿用该身份"),
    Column("enabled", Boolean, nullable=False, comment="是否启用"),
    Column("revision", Integer, nullable=False, comment="编辑版本，防止覆盖并发修改"),
    Column("configuration", JSON, nullable=False, comment="单据范围、每日时间和回扫天数，不含凭据"),
    Column("next_run_at", TIMESTAMP, comment="下一次触发时间，UTC"),
    *timestamps(),
    UniqueConstraint("scope_key", name="uq_sync_ns_plan_scope"),
    comment="NS 来源（报关单、子采购单）每日定时同步计划",
    **table_options,
)
