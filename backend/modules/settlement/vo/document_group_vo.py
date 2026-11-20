"""资料组当前依据与进度；金额按组内全部成员计算。"""

from backend.core.dto import StrictModel

from .batch_vo import Action


class DocumentGroupMember(StrictModel):
    declarationNo: str
    recordNo: str
    exportDate: str = ""
    consignee: str
    exportCompany: str
    currency: str
    amount: str
    salesOrders: list[str]


class DocumentGroup(StrictModel):
    id: int
    kind: str = "single"
    merge: Action = Action(allowed=False, reason="")
    package: Action = Action(allowed=False, reason="")
    packageUrl: str = ""
    groupNo: str
    consignee: str
    currency: str
    amount: str
    members: list[DocumentGroupMember]
    status: str
    statusLabel: str
    edit: Action
    updateSource: Action = Action(allowed=False, reason="")
    createdBy: str
    createdAt: str


class DocumentGroupList(StrictModel):
    items: list[DocumentGroup]
    total: int
    page: int
    pageSize: int


class GroupBasisPreview(StrictModel):
    groupId: int
    oldConsignee: str
    oldCurrency: str
    newConsignee: str
    newCurrency: str
    declarationCount: int
    amount: str
    token: str
    update: Action


class DocumentMergeResult(StrictModel):
    group: DocumentGroup | None = None
