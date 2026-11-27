"""供应商合并通知：带完整范围版本与幂等请求编号，不能由前端指定任意成员。"""

from uuid import UUID

from pydantic import Field

from .notification_dto import NotificationDraft, NotificationRecord


class SupplierNotificationDraft(NotificationDraft):
    scopeRevision: str = Field(pattern=r"^[0-9a-f]{64}$")
    requestId: UUID = Field(strict=False)


class SupplierNotificationRecord(NotificationRecord):
    scopeRevision: str = Field(pattern=r"^[0-9a-f]{64}$")
