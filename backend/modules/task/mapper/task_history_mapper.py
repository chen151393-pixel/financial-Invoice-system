"""合并状态事件与合同获取事实；按完整时间和原记录顺序编号，再倒序展示。"""

from datetime import datetime

from ..vo.task_history_vo import TaskHistoryRecord
from .task_mapper import events


def ordered(records):
    def key(record):
        # 时间保留数据库微秒精度。同刻先获取合同，再记录状态；事件按递增主键判定先后。
        return (
            datetime.fromisoformat(record.at),
            record.kind == "event",
            tuple(int(value) for value in record.id.split(":")[1:]),
        )

    chronological = sorted(records, key=key)
    return [
        record.model_copy(update={"sequence": index})
        for index, record in reversed(list(enumerate(chronological, 1)))
    ]


def records(event_rows, documents, actor_names):
    history = [
        TaskHistoryRecord(
            id=f"event:{row['id']}",
            kind="event",
            at=event.at,
            label=event.label,
            actor=event.actor,
            actorName=actor_names.get(event.actor, event.actor),
            reason=event.reason,
        )
        for row, event in zip(event_rows, events(event_rows), strict=True)
    ]
    history.extend(
        TaskHistoryRecord(
            id=f"document:{doc.taskId}:{doc.orderId}",
            kind="document",
            at=doc.downloadedAt,
            label=f"获取子采购合同：{doc.orderNumber}",
            environment=doc.environment,
            nsId=doc.nsId,
            archivedAt=doc.archivedAt,
            archivePath=doc.archivePath,
            sha256=doc.sha256,
        )
        for doc in documents
        if doc.downloadedAt
    )
    return ordered(history)
