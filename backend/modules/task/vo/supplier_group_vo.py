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


class SupplierNotify(StrictModel):
    """是否开启供应商通知；关闭后财务审核通过不生成该供应商的开票任务。"""

    enabled: bool
    revision: int
    updatedBy: str = ""
    updatedAt: str | None = None


class SupplierProfile(SupplierOption):
    nsInternalId: str
    notify: SupplierNotify


class SupplierProfileList(StrictModel):
    items: list[SupplierProfile]
    total: int
    page: int
    pageSize: int
    pages: int
    manage: Capability
    # 档案概况（不受关键字与状态筛选影响）：all 全部、bound 已绑定开票群、unbound 未绑定、notifyOff 已关闭通知
    counts: dict[str, int]


class WecomGroupItem(GroupItem):
    matchReason: str = ""
    memberCount: int
    createdAt: str | None


class WecomGroupList(StrictModel):
    directoryUpdatedAt: str | None = None
    directoryStale: bool = False
    directoryRefreshing: bool = False
    directoryRefreshError: str = ""
    unavailableCount: int
    items: list[WecomGroupItem]
    total: int
    page: int
    pageSize: int
    pages: int
