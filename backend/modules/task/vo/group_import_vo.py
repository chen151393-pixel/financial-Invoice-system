"""导入预览、外部群目录和确认结果。"""

from backend.core.dto import StrictModel

from .capability import Capability
from .supplier_group_vo import GroupItem, SupplierOption


class ExternalGroupView(GroupItem):
    memberCount: int | None
    department: str
    createdAt: str


class Candidate(SupplierOption):
    reason: str


class PreviewRow(StrictModel):
    rowNo: int
    groupName: str
    group: ExternalGroupView | None = None
    issue: str = ""
    catalogRevision: int = 0
    candidates: list[Candidate] = []
    candidateCount: int = 0


class ImportReceipt(StrictModel):
    importId: str
    filename: str
    total: int
    valid: int
    invalid: int
    matched: int
    unmatched: int
    status: str
    confirm: Capability


class SuggestedAssociation(StrictModel):
    rowNo: int
    supplier: SupplierOption
    replaceExisting: bool = False


class PreviewPage(ImportReceipt):
    suggestions: list[SuggestedAssociation]
    items: list[PreviewRow]
    page: int
    pageSize: int
    pages: int


class CatalogItem(ExternalGroupView):
    revision: int
    filename: str
    updatedAt: str
    suppliers: list[SupplierOption]


class CatalogPage(StrictModel):
    items: list[CatalogItem]
    total: int
    page: int
    pageSize: int
    pages: int
    manage: Capability


class ImportResult(StrictModel):
    importId: str
    imported: int
    bound: int
    skipped: int
    message: str
