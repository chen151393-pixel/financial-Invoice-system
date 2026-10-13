"""供应商通知响应：人工登记不代表企微回执、供应商已读或已开票。"""

from backend.core.dto import StrictModel

from .capability import Capability


class NotificationEvent(StrictModel):
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
