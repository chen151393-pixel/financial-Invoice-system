"""task：回签合同分片上传与持久归档队列，不保存文件正文。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, identifier, table_options, timestamps

revision = "0030_task_signed_upload_jobs"
down_revision = "0029_source_sales_orders"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_signed_upload_jobs",
        sa.Column("id", identifier(36), primary_key=True, comment="服务端生成的上传文件 ID"),
        sa.Column("batch_id", identifier(36), nullable=False, comment="客户端请求 ID，限定在操作者内幂等"),
        sa.Column("actor", identifier(190), nullable=False, comment="认证操作者"),
        sa.Column("position", sa.Integer, nullable=False, comment="批内文件顺序"),
        sa.Column("manifest_sha256", sa.String(64), nullable=False, comment="原始批次清单摘要"),
        sa.Column("filename", sa.String(255), nullable=False, comment="原始文件名，仅用于展示和匹配"),
        sa.Column(
            "order_no", sa.String(150), nullable=False, server_default="", comment="人工指定或已匹配单号"
        ),
        sa.Column("size_bytes", ID, nullable=False, comment="声明的原文件字节数"),
        sa.Column("received_bytes", ID, nullable=False, server_default="0", comment="已持久接收字节数"),
        sa.Column("sha256", sa.String(64), comment="完整接收后的文件摘要"),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            comment="队列状态：uploading/queued/running/saved/unmatched/ambiguous/conflict/failed",
        ),
        sa.Column(
            "reason", sa.String(500), nullable=False, server_default="", comment="中文处理结果或失败原因"
        ),
        sa.Column("archive_path", sa.String(1000), comment="最终共享盘路径"),
        *timestamps(),
        sa.UniqueConstraint("actor", "batch_id", "position", name="uq_task_signed_upload_position"),
        sa.CheckConstraint(
            "status IN ('uploading','queued','running','saved','unmatched','ambiguous','conflict','failed')",
            name="ck_task_signed_upload_status",
        ),
        comment="回签合同上传及后台归档队列，仅保存元数据，文件另存持久暂存目录",
        **table_options,
    )
    op.create_index("ix_task_signed_upload_pending", "task_signed_upload_jobs", ["status", "created_at"])


def downgrade():
    raise RuntimeError("上传队列可能存在尚未归档的原件，不能降级删除；请保留数据")
