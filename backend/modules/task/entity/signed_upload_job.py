"""回签合同持久上传队列：每行一个文件，批次按 batch_id 汇总。"""

from sqlalchemy import CheckConstraint, Column, Index, Integer, String, Table, UniqueConstraint

from backend.core.schema import ID, identifier, schema_metadata, table_options, timestamps

signed_upload_jobs = Table(
    "task_signed_upload_jobs",
    schema_metadata,
    Column("id", identifier(36), primary_key=True, comment="服务端生成的上传文件 ID"),
    Column("batch_id", identifier(36), nullable=False, comment="客户端请求 ID，限定在操作者内幂等"),
    Column("actor", identifier(190), nullable=False, comment="认证操作者"),
    Column("position", Integer, nullable=False, comment="批内文件顺序"),
    Column("manifest_sha256", String(64), nullable=False, comment="原始批次清单摘要"),
    Column("filename", String(255), nullable=False, comment="原始文件名，仅用于展示和匹配"),
    Column("order_no", String(150), nullable=False, server_default="", comment="人工指定或已匹配单号"),
    Column("size_bytes", ID, nullable=False, comment="声明的原文件字节数"),
    Column("received_bytes", ID, nullable=False, server_default="0", comment="已持久接收字节数"),
    Column("sha256", String(64), comment="完整接收后的文件摘要"),
    Column(
        "status",
        String(20),
        nullable=False,
        comment="队列状态：uploading/queued/running/saved/unmatched/ambiguous/conflict/failed",
    ),
    Column("reason", String(500), nullable=False, server_default="", comment="中文处理结果或失败原因"),
    Column("archive_path", String(1000), comment="最终共享盘路径"),
    *timestamps(),
    UniqueConstraint("actor", "batch_id", "position", name="uq_task_signed_upload_position"),
    Index("ix_task_signed_upload_pending", "status", "created_at"),
    CheckConstraint(
        "status IN ('uploading','queued','running','saved','unmatched','ambiguous','conflict','failed')",
        name="ck_task_signed_upload_status",
    ),
    comment="回签合同上传及后台归档队列，仅保存元数据，文件另存持久暂存目录",
    **table_options,
)
