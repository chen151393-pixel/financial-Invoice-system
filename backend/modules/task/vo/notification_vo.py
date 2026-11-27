"""供应商通知响应：人工登记不代表企微回执、供应商已读或已开票。"""

from typing import Literal

from backend.core.dto import StrictModel

from .capability import Capability


class NotificationEvent(StrictModel):
    taskId: str = ""
    recordNumber: str = ""
    channel: str = "manual"
    revision: int
    actor: str
    at: str
    groupName: str
    employee: str
    message: str
    sentAt: str | None = None
    recordedBy: str = ""
    note: str = ""
    attachments: list[str] = []


class NotificationGroup(StrictModel):
    groupName: str
    chatId: str
    employee: str
    userid: str
    revision: int


class NotificationDetail(StrictModel):
    scopeReason: str = ""
    taskIds: list[str] = []
    attachments: list[str] = []
    supplierGroup: NotificationGroup | None = None
    groupConfigReason: str = ""
    revision: int
    groupName: str
    employee: str
    message: str
    defaultMessage: str
    statusLabel: str
    edit: Capability
    record: Capability
    send: Capability
    history: list[NotificationEvent]


class NotificationBatchTarget(StrictModel):
    """列表本次可登记的原任务，仅含确认窗口所需信息。"""

    id: str
    supplier: str
    recordNumber: str
    orderNumbers: list[str]


class NotificationBatchItem(StrictModel):
    id: str
    reason: str = ""


class NotificationBatchResult(StrictModel):
    """批量登记逐个任务的结果；跳过的任务附原因，不影响其他任务。"""

    recorded: list[NotificationBatchItem]
    skipped: list[NotificationBatchItem]


class NotificationGroupOutcome(StrictModel):
    id: str
    status: Literal["recorded", "skipped", "unknown"]
    taskIds: list[str]
    reason: str = ""


class NotificationGroupBatchResult(StrictModel):
    groups: list[NotificationGroupOutcome]
    recordedGroups: int
    skippedGroups: int
    unknownGroups: int
    recordedTasks: int
