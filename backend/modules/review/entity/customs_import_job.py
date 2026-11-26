"""海关回执异步导入作业；原文件暂存磁盘，不保存到数据库。"""

from sqlalchemy import CHAR, JSON, CheckConstraint, Column, Index, String, Table

from backend.core.schema import ID, schema_metadata, table_options, timestamps

customs_import_jobs = Table(
    "review_customs_import_jobs",
    schema_metadata,
    Column("id", ID, primary_key=True, autoincrement=True, comment="导入作业主键"),
    Column("file_name", String(255), nullable=False, comment="上传文件名"),
    Column("upload_key", CHAR(32), nullable=False, comment="暂存文件随机标识，不使用上传文件名拼路径"),
    Column("actor", String(190), nullable=False, comment="提交导入的认证身份"),
    Column(
        "status",
        String(20),
        nullable=False,
        comment="pending待处理；running处理中；completed成功；failed失败",
    ),
    Column("error_message", String(1000), comment="失败原因；不回显文件内容和服务器路径"),
    Column("result", JSON, comment="成功提交后的导入统计及逐张结果"),
    *timestamps(),
    CheckConstraint(
        "status IN ('pending','running','completed','failed')", name="ck_review_customs_import_status"
    ),
    Index("ix_review_customs_import_pending", "status", "id"),
    Index("ix_review_customs_import_actor", "actor", "id"),
    comment="海关回执异步导入队列及结果",
    **table_options,
)
