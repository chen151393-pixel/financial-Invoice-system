"""企业与客户群的持久占用，重启不清空。"""

from sqlalchemy import Column, ForeignKey, Table

from backend.core.schema import ID, identifier, schema_metadata, table_options, timestamps

notification_group_guards = Table(
    "task_notification_group_guards",
    schema_metadata,
    Column("corp_id", identifier(190), primary_key=True, comment="企微企业身份"),
    Column("chat_id", identifier(190), primary_key=True, comment="客户群身份"),
    Column(
        "active_delivery_id",
        ID,
        ForeignKey("task_notification_deliveries.id", name="fk_task_group_guard_delivery"),
        comment="未决发送执行",
    ),
    *timestamps(),
    comment="同群跨任务发送互斥守卫",
    **table_options,
)
