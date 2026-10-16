"""任务状态历史，只追加。"""

from sqlalchemy import CHAR, JSON, Column, ForeignKey, Index, String, Table

from backend.core.schema import ID, TIMESTAMP, schema_metadata, table_options, timestamps

events = Table(
    "task_events",
    schema_metadata,
    Column(
        "id", ID, comment="本地自增主键；与 NS 内部 ID、单号分开保存", primary_key=True, autoincrement=True
    ),
    Column(
        "task_id",
        ID,
        ForeignKey("task_tasks.id", name="fk_task_event_task"),
        comment="开票任务 ID，指向 task_tasks.id",
        nullable=False,
    ),
    Column("from_status", String(24), comment="事件发生前任务状态；首次创建可为空"),
    Column("to_status", String(24), comment="事件发生后任务状态；证据类事件可与原状态相同", nullable=False),
    Column("reason", String(300), comment="状态变化或人工决定的中文原因"),
    Column("actor", String(200), nullable=False, comment="事件操作者或 system"),
    Column("occurred_at", TIMESTAMP, comment="事件发生时间，UTC", nullable=False),
    Column(
        "event_type",
        String(40),
        comment="事件类型：如 status_changed 状态变化、evidence_linked 补关联证据、difference_closed 差异结束",
        nullable=False,
        server_default="status_changed",
    ),
    Column("task_line_id", ID, comment="事件涉及的任务行 ID，逻辑指向 task_lines.id"),
    Column("details", JSON, comment="结构化事件详情；差异结束保存依据 ID、台账摘要、数量差和金额差"),
    Column("request_id", CHAR(36), comment="幂等请求编号，防止同一操作重试时重复生成记录"),
    *timestamps(),
    Index("uq_task_event_request", "request_id", unique=True),
    Index("ix_task_event_task", "task_id", "occurred_at"),
    comment="任务状态历史，只追加",
    **table_options,
)
