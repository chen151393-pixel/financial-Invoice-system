"""review：后台导入队列；回退前必须确认没有排队、运行或已完成的作业记录。"""

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, table_options, timestamps

revision = "0057_review_customs_import_jobs"
down_revision = "0056_review_customs_difference_kinds"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_customs_import_jobs",
        sa.Column("id", ID, primary_key=True, autoincrement=True, comment="导入作业主键"),
        sa.Column("file_name", sa.String(255), nullable=False, comment="上传文件名"),
        sa.Column(
            "upload_key", sa.CHAR(32), nullable=False, comment="暂存文件随机标识，不使用上传文件名拼路径"
        ),
        sa.Column("actor", sa.String(190), nullable=False, comment="提交导入的认证身份"),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            comment="pending待处理；running处理中；completed成功；failed失败",
        ),
        sa.Column("error_message", sa.String(1000), comment="失败原因；不回显文件内容和服务器路径"),
        sa.Column("result", sa.JSON, comment="成功提交后的导入统计及逐张结果"),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed')", name="ck_review_customs_import_status"
        ),
        comment="海关回执异步导入队列及结果",
        **table_options,
    )
    op.create_index("ix_review_customs_import_pending", "review_customs_import_jobs", ["status", "id"])
    op.create_index("ix_review_customs_import_actor", "review_customs_import_jobs", ["actor", "id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM review_customs_import_jobs")).scalar():
        raise RuntimeError("海关导入作业已有数据，不能自动删除导入历史")
    op.drop_table("review_customs_import_jobs")
