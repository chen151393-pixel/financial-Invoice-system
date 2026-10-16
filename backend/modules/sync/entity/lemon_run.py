"""柠檬云手动拉取的持久请求与提交结果。"""

from sqlalchemy import JSON, Column, Date, Index, String, Table, UniqueConstraint

from backend.core.schema import ID, identifier, schema_metadata, table_options, timestamps

lemon_runs = Table(
    "sync_lemon_runs",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="同步记录主键"),
    Column("scope_key", identifier(64), nullable=False, comment="环境、应用与认证身份摘要"),
    Column("request_id", identifier(36), nullable=False, comment="调用方请求编号，重复提交只查询原结果"),
    Column("asid", identifier(32), nullable=False, comment="本次授权账套编号"),
    Column("account_name", String(255), nullable=False, comment="本次授权账套名称快照"),
    Column("start_date", Date, nullable=False, comment="起始开票日期"),
    Column("end_date", Date, nullable=False, comment="结束开票日期"),
    Column(
        "status",
        identifier(20),
        nullable=False,
        comment="running执行中或待核实；completed已提交；failed未保存",
    ),
    Column("result", JSON, nullable=True, comment="已提交的实际保存统计"),
    Column("error", String(500), nullable=True, comment="脱敏失败原因"),
    *timestamps(),
    UniqueConstraint("scope_key", "request_id", name="uq_sync_lemon_request"),
    Index("ix_sync_lemon_scope_status", "scope_key", "status"),
    comment="柠檬云手动拉票记录与结果，不保存令牌",
    **table_options,
)
