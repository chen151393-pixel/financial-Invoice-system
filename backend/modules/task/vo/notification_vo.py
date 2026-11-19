"""供应商通知响应：人工登记不代表企微回执、供应商已读或已开票。"""

from backend.core.dto import StrictModel

from .capability import Capability


class NotificationEvent(StrictModel):
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


class NotificationBatchItem(StrictModel):
    id: str
    reason: str = ""


class NotificationBatchResult(StrictModel):
    """批量登记逐个任务的结果；跳过的任务附原因，不影响其他任务。"""

    recorded: list[NotificationBatchItem]
    skipped: list[NotificationBatchItem]
