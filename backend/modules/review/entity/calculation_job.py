"""按账套合并重算请求；代次防止后台旧结果覆盖新来源。"""

from sqlalchemy import CheckConstraint, Column, Integer, String, Table, UniqueConstraint

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

calculation_jobs = Table(
    "review_calculation_jobs",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="计算队列本地主键"),
    Column("ns_account", String(100), nullable=False, comment="需要更新财务查询快照的 NS 账套"),
    Column("requested_revision", Integer, nullable=False, comment="同步或审核提交时递增的请求代次"),
    Column("completed_revision", Integer, nullable=False, server_default="0", comment="已原子发布的代次"),
    Column("calculation_key", String(100), nullable=False, server_default="", comment="算法版本及人民币容差"),
    Column("attempts", Integer, nullable=False, server_default="0", comment="当前代次连续失败次数"),
    Column("retry_at", TIMESTAMP, comment="失败后最早重试时间，UTC"),
    Column("last_error", String(300), nullable=False, server_default="", comment="计算失败的中文说明"),
    *timestamps(),
    UniqueConstraint("ns_account", name="uq_review_calculation_account"),
    CheckConstraint(
        "requested_revision >= completed_revision AND completed_revision >= 0",
        name="ck_review_calculation_revision",
    ),
    comment="财务后台计算队列，按账套合并请求并持久重试",
    **table_options,
)
