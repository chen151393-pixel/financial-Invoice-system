"""任务流转记录：后端确定操作步骤与展示顺序，保留原审计身份。"""

from typing import Literal

from backend.core.dto import StrictModel


class TaskHistoryRecord(StrictModel):
    id: str
    sequence: int = 0
    kind: Literal["event", "document"]
    at: str
    label: str
    actor: str = ""
    actorName: str = ""
    reason: str = ""
    environment: str = ""
    nsId: str = ""
    archivedAt: str | None = None
    archivePath: str | None = None
    sha256: str = ""
