"""供应商人员分工的生效历史；每次调整只追加一行。"""

from sqlalchemy import Column, Date, Index, String, Table

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, utc_now

supplier_owners = Table(
    "task_supplier_owners",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="记录主键，同时用于并发版本校验"),
    Column("supplier_id", ID, nullable=False, comment="source 供应商本地主键，跨模块不建外键"),
    Column("company_id", ID, nullable=False, comment="source 采购公司本地主键，跨模块不建外键"),
    Column("member_id", ID, nullable=False, comment="identity 人员本地主键，跨模块不建外键"),
    Column("member_name", String(200), nullable=False, comment="人员姓名快照，保留历史显示"),
    Column("effective_date", Date, nullable=False, comment="人员分工生效日期，北京时间；同日取较新记录"),
    Column("reason", String(300), nullable=False, comment="新增或调整原因"),
    Column("actor", String(200), nullable=False, comment="来自认证身份的操作者"),
    Column(
        "created_at",
        TIMESTAMP,
        nullable=False,
        server_default=utc_now(),
        comment="记录保存时间，UTC；历史只追加",
    ),
    Index("ix_task_owner_effective", "supplier_id", "company_id", "effective_date", "id"),
    comment="供应商与采购抬头的人员分工历史；不另建当前关系、版本或任务归属表",
    **table_options,
)
