"""NS 报关/子采购按批后台保存的持久请求与结果；定时计划的分页记录指向所属批次。"""

from sqlalchemy import JSON, Column, ForeignKey, Index, String, Table, UniqueConstraint

from backend.core.schema import ID, identifier, schema_metadata, table_options, timestamps

ns_runs = Table(
    "sync_ns_runs",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="同步批次记录主键"),
    Column("scope_key", identifier(64), nullable=False, comment="NS 账户与认证身份摘要"),
    Column("request_id", identifier(36), nullable=False, comment="调用方请求编号，重复提交只查询原结果"),
    Column("kind", identifier(32), nullable=False, comment="sub-purchase-orders 或 customs-declarations"),
    Column("request", JSON, nullable=False, comment="本批分页与日期条件快照"),
    Column(
        "status",
        identifier(20),
        nullable=False,
        comment="running执行中或待核实；completed/partial/interrupted见逐单结果；failed未写入；unknown待核实",
    ),
    Column("result", JSON, nullable=True, comment="本批实际保存结果，含逐单状态"),
    Column("error", String(500), nullable=True, comment="脱敏失败原因"),
    Column(
        "run_id",
        ID,
        ForeignKey("sync_runs.id", name="fk_sync_ns_run_batch"),
        comment="所属定时计划批次；手动按批保存为空",
    ),
    *timestamps(),
    UniqueConstraint("scope_key", "request_id", name="uq_sync_ns_request"),
    Index("ix_sync_ns_scope_status", "scope_key", "status"),
    Index("ix_sync_ns_run_batch", "run_id", "status"),
    comment="NS 来源按批后台保存记录与结果，不保存令牌",
    **table_options,
)
