"""供应商人员关联响应；当前负责人、未来变更与历史快照明确区分。"""

from pydantic import Field

from backend.core.dto import StrictModel


class OwnerVersion(StrictModel):
    id: str
    memberId: str
    memberName: str
    effectiveDate: str
    revision: int
    reason: str
    actor: str
    createdAt: str


class OwnerItem(StrictModel):
    supplierId: int
    supplierName: str
    nsInternalId: str
    account: str
    companyId: int
    companyName: str
    revision: int
    current: OwnerVersion | None = None
    scheduled: list[OwnerVersion] = Field(default_factory=list)
    status: str


class OwnerList(StrictModel):
    items: list[OwnerItem]
    total: int
    page: int
    pageSize: int
    pages: int
    today: str


class OwnerOption(StrictModel):
    id: int
    name: str
    account: str = ""


class OwnerOptions(StrictModel):
    suppliers: list[OwnerOption]
    companies: list[OwnerOption]
    members: list[OwnerOption]
    today: str


class OwnerHistory(StrictModel):
    items: list[OwnerVersion]


class OwnerImpact(StrictModel):
    pairCount: int
    openTaskCount: int
    transferAllowed: bool
    transferReason: str
    memberName: str
    effectiveDate: str
    previewToken: str


class OwnerSaved(StrictModel):
    saved: int
    transferredTasks: int
