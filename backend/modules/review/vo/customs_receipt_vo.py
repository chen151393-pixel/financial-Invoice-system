"""海关回执响应：比对结果、文案与计数均由服务器给出；数量与金额为十进制字符串。"""

from typing import Literal

from backend.core.dto import StrictModel

MatchStatus = Literal["matched", "split_matched", "different", "ns_missing", "ns_duplicate"]
GroupStatus = Literal[
    "matched", "split", "merged", "quantity_mismatch", "unit_mismatch", "missing_in_ns", "missing_in_customs"
]


class CustomsItem(StrictModel):
    itemNo: str
    hsCode: str
    name: str
    specification: str
    contractNo: str
    taxType: str
    checkStatus: str
    quantity: str
    unit: str
    currency: str
    total: str
    usdFob: str
    legalQuantity: str
    legalUnit: str
    customsDoc: str
    usageFlag: str


class NsLine(StrictModel):
    id: int
    lineNo: str
    itemCode: str
    name: str
    specification: str
    quantity: str
    unit: str


class CompareGroup(StrictModel):
    status: GroupStatus
    label: str
    note: str
    # 一致类（一致、拆行一致、合并一致）为 True；页面据此选择徽标语气，不自行判断
    consistent: bool
    nsLines: list[NsLine]
    items: list[CustomsItem]


class Consignee(StrictModel):
    value: str
    # saved：已随 NS 报关单保存；empty：回执未提供；pending：待找到 NS 报关单后关联
    state: Literal["saved", "empty", "pending"]
    label: str
    note: str


class CustomsApproval(StrictModel):
    token: str
    approved: bool
    label: str
    allowed: bool
    autoAllowed: bool
    reason: str
    approvedBy: str = ""
    approvedAt: str = ""
    note: str = ""


class CustomsReceipt(StrictModel):
    id: int
    declarationNo: str
    exportDate: str
    taxType: str
    customsDoc: str
    usageFlag: str
    itemCount: int
    nsLineCount: int | None
    nsRecordNo: str
    consignee: Consignee
    status: MatchStatus
    statusLabel: str
    statusNote: str
    matchedAt: str
    importedAt: str
    fileName: str
    revision: int
    groups: list[CompareGroup]
    approval: CustomsApproval


class CustomsApproveOutcome(StrictModel):
    id: int
    declarationNo: str = ""
    reason: str = ""


class CustomsApproveResult(StrictModel):
    approved: list[CustomsApproveOutcome]
    skipped: list[CustomsApproveOutcome]


class CustomsCounts(StrictModel):
    receipts: int
    items: int
    # 明细一致（含拆行/合并一致）
    matched: int
    # 其中拆行/合并一致
    splitMatched: int
    different: int
    nsMissing: int


class CustomsReceiptList(StrictModel):
    items: list[CustomsReceipt]
    counts: CustomsCounts
    total: int
    page: int
    pageSize: int
    pages: int


class ImportedDeclaration(StrictModel):
    declarationNo: str
    itemCount: int
    # created：新增；replaced：内容变化已换版；unchanged：与已导入内容相同
    result: Literal["created", "replaced", "unchanged"]
    resultLabel: str
    status: MatchStatus
    statusLabel: str
    consignee: Consignee


class CustomsImportResult(StrictModel):
    fileName: str
    rows: int
    columns: list[str]
    ignoredColumns: list[str]
    created: int
    replaced: int
    unchanged: int
    declarations: list[ImportedDeclaration]


class RematchResult(StrictModel):
    rematched: int
