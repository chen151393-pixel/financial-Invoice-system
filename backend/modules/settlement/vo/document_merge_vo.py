"""合并候选与条件，金额、资格及合并后合同规划均由后端返回。"""

from backend.core.dto import StrictModel

from .batch_vo import Action
from .document_group_vo import DocumentGroupMember


class MergeCandidate(DocumentGroupMember):
    groupId: int | None
    groupNo: str
    source: bool
    sharedBill: bool
    select: Action


class DocumentMergeCandidates(StrictModel):
    source: MergeCandidate
    items: list[MergeCandidate]
    total: int
    page: int
    pageSize: int


class MergeCheck(StrictModel):
    key: str
    label: str
    passed: bool
    detail: str


class MergeBillOption(StrictModel):
    id: int
    blNo: str
    fileName: str


class MergeContractPlan(StrictModel):
    key: str
    contractNo: str
    sellerName: str
    declarationNos: list[str]
    currency: str
    amount: str


class DocumentMergePreview(StrictModel):
    selected: list[DocumentGroupMember]
    selectedCount: int
    currency: str
    amount: str
    checks: list[MergeCheck]
    merge: Action
    token: str
    sourceBills: list[MergeBillOption]
    sharedBillId: int
    existingBillCount: int
    existingContractCount: int
    contracts: list[MergeContractPlan]
