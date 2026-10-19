"""同步批次：复用基线 sync_runs，phase 区分排队、执行及待核实。"""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)

from backend.core.schema import ID, TIMESTAMP, identifier, schema_metadata, table_options, timestamps

sync_runs = Table(
    "sync_runs",
    schema_metadata,
    Column(
        "id", ID, primary_key=True, autoincrement=True, comment="本地自增主键；与 NS 内部 ID、单号分开保存"
    ),
    Column(
        "source",
        String(32),
        nullable=False,
        comment="同步来源：ns_customs 报关；ns_purchase 采购；lemon_invoice 发票",
    ),
    Column("account", String(100), nullable=False, comment="同步来源账套；随 source 表示 NS 或柠檬云账套"),
    Column("trigger_type", String(16), nullable=False, comment="触发方式：schedule 定时；manual 手动"),
    Column(
        "status",
        String(16),
        nullable=False,
        comment="同步状态：running 运行中；succeeded 成功；partial 部分成功；failed 失败",
    ),
    Column("window_start", TIMESTAMP, comment="本次同步的时间窗口起点，UTC"),
    Column("window_end", TIMESTAMP, comment="本次同步的时间窗口终点，UTC"),
    *[
        Column(
            name,
            Integer,
            nullable=False,
            server_default=text("0"),
            comment={
                "fetched_count": "本次取得的来源记录数",
                "created_count": "本次新增记录数",
                "updated_count": "本次更新记录数",
                "failed_count": "本次失败记录数",
            }[name],
        )
        for name in ("fetched_count", "created_count", "updated_count", "failed_count")
    ],
    Column("message", Text, comment="同步结果或失败原因，不记录凭据"),
    Column("started_by", String(200), nullable=False, comment="发起操作者或 scheduler"),
    Column("started_at", TIMESTAMP, nullable=False, comment="同步运行开始时间，UTC"),
    Column("finished_at", TIMESTAMP, comment="同步运行结束时间，UTC"),
    Column("scope_key", identifier(64), comment="后台任务身份范围"),
    Column("request_id", identifier(36), comment="幂等提交编号"),
    Column("plan_id", ID, ForeignKey("sync_lemon_plans.id", name="fk_sync_run_plan"), comment="来源计划"),
    Column("phase", identifier(20), comment="后台任务阶段"),
    Column("configuration", JSON, comment="不可变执行条件及授权绑定摘要"),
    *timestamps(),
    UniqueConstraint("scope_key", "request_id", name="uq_sync_run_request"),
    Index("ix_sync_run_source", "source", "account", "started_at"),
    Index("ix_sync_run_scope_phase", "scope_key", "phase"),
    CheckConstraint("status IN ('running','succeeded','partial','failed')", name="ck_sync_run_status"),
    CheckConstraint("trigger_type IN ('schedule','manual')", name="ck_sync_run_trigger"),
    comment="同步运行记录",
    **table_options,
)
