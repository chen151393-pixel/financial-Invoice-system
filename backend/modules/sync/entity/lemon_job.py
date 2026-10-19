"""账套日期分片；每片对应一个原子保存请求，拆分父片不计入保存统计。"""

from sqlalchemy import Column, Date, ForeignKey, Index, String, Table, UniqueConstraint

from backend.core.schema import ID, identifier, schema_metadata, table_options, timestamps

lemon_jobs = Table(
    "sync_lemon_jobs",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="分片主键"),
    Column(
        "run_id",
        ID,
        ForeignKey("sync_runs.id", name="fk_sync_lemon_job_run"),
        nullable=False,
        comment="所属批次",
    ),
    Column("request_id", identifier(36), nullable=False, comment="对应 sync_lemon_runs 的原子请求编号"),
    Column("asid", identifier(32), nullable=False, comment="授权账套编号"),
    Column("account_name", String(255), nullable=False, comment="发现时的账套名称"),
    Column("start_date", Date, nullable=False, comment="起始开票日期"),
    Column("end_date", Date, nullable=False, comment="结束开票日期"),
    Column(
        "status",
        identifier(20),
        nullable=False,
        comment="分片状态：queued/running/completed/failed/unknown/split",
    ),
    Column("error", String(500), comment="脱敏原因"),
    *timestamps(),
    UniqueConstraint("request_id", name="uq_sync_lemon_job_request"),
    Index("ix_sync_lemon_job_run", "run_id", "status"),
    comment="柠檬云后台账套拉取分片",
    **table_options,
)
