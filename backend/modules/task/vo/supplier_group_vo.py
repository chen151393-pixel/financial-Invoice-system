"""供应商群配置响应。"""

from backend.core.dto import StrictModel

from .capability import Capability


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
    manage: Capability


class SupplierItem(StrictModel):
    account: str
    supplierId: str
    supplierName: str


class SupplierOption(SupplierItem):
    binding: GroupBinding | None = None


class SupplierList(StrictModel):
    items: list[SupplierOption]
    total: int
    page: int
    pageSize: int
    pages: int


class SupplierProfile(SupplierOption):
    nsInternalId: str


class SupplierProfileList(StrictModel):
    items: list[SupplierProfile]
    total: int
    page: int
    pageSize: int
    pages: int
    manage: Capability


class WecomGroupItem(GroupItem):
    matchReason: str = ""
    memberCount: int
    createdAt: str | None


class WecomGroupList(StrictModel):
    unavailableCount: int
    items: list[WecomGroupItem]
    total: int
    page: int
    pageSize: int
    pages: int
