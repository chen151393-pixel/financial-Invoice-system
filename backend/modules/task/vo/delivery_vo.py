"""企微发送视图，不返回服务器内部路径和凭证。"""

from backend.core.dto import StrictModel

from .capability import Capability


class DeliveryFile(StrictModel):
    filename: str
    sha256: str
    size: int


class DeliveryPreview(StrictModel):
    revision: int
    groupRevision: int
    snapshotSha256: str
    supplier: str
    company: str
    orderNumbers: list[str]
    corpId: str
    chatId: str
    groupName: str
    employee: str
    userid: str
    message: str
    files: list[DeliveryFile]
    submit: Capability


class DeliveryView(StrictModel):
    autoPoll: bool
    id: str
    revision: int
    status: str
    statusLabel: str
    corpId: str
    chatId: str
    groupName: str
    employee: str
    userid: str
    message: str
    files: list[DeliveryFile]
    createdAt: str
    submittedAt: str | None
    sentAt: str | None
    lastCheckedAt: str | None
    nextCheckAt: str | None
    msgid: str
    error: str
    refresh: Capability
    reconcile: Capability


class DeliveryList(StrictModel):
    items: list[DeliveryView]


class DeliveryCandidate(StrictModel):
    candidateId: str
    evidenceSha256: str
    description: str


class DeliveryCandidates(StrictModel):
    items: list[DeliveryCandidate]
    reason: str
