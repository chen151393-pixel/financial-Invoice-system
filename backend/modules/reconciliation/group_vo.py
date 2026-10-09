"""供应商群配置的展示契约。"""

from backend.core.dto import StrictModel

from .task_vo import TaskCapability


class GroupItem(StrictModel):
    groupName: str
    chatId: str
    employee: str
    userid: str


class GroupBinding(GroupItem):
    account: str
    supplierId: str
    supplierName: str
    revision: int
    enabled: bool
    updatedAt: str


class GroupList(StrictModel):
    items: list[GroupBinding]
    total: int
    page: int
    pageSize: int
    pages: int
    manage: TaskCapability


class SupplierItem(StrictModel):
    account: str
    supplierId: str
    supplierName: str


class SupplierList(StrictModel):
    items: list[SupplierItem]
    total: int
    page: int
    pageSize: int
    pages: int


class WecomGroupItem(GroupItem):
    memberCount: int
    createdAt: str | None


class WecomGroupList(StrictModel):
    unavailableCount: int
    items: list[WecomGroupItem]
    total: int
    page: int
    pageSize: int
    pages: int
