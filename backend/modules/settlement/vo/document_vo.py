"""批次资料响应：齐全度、缺项与可操作判断由后端给出；金额为十进制字符串。"""

from backend.core.dto import StrictModel

from .batch_vo import Action


class Bill(StrictModel):
    id: int
    fileName: str
    fileUrl: str
    blNo: str
    portOfLoading: str
    portOfDischarge: str
    onBoardDate: str
    declarationNos: list[str]
    missing: list[str]
    parseNote: str
    uploadedBy: str
    uploadedAt: str


class Contract(StrictModel):
    key: str = ""
    id: int
    contractNo: str
    fileUrl: str
    contractDate: str
    currency: str
    amount: str
    declarationNos: list[str]
    buyerName: str
    sellerName: str
    tradeTerm: str
    portOfLoading: str
    portOfDestination: str
    stale: bool
    stampNote: str
    generatedBy: str
    generatedAt: str


class PlannedContract(StrictModel):
    key: str = ""
    contractNo: str
    contractDate: str
    portOfLoading: str
    portOfDestination: str
    buyerName: str
    sellerName: str
    currency: str
    amount: str
    declarationNos: list[str]


class PartyOption(StrictModel):
    id: int
    name: str
    hasStamp: bool


class ContractDefaults(StrictModel):
    sellerPartyId: int | None
    tradeTerm: str
    paymentTermsCn: str
    paymentTermsEn: str


class DeclarationFile(StrictModel):
    declarationNo: str
    recordNo: str
    status: str
    statusLabel: str
    archived: bool
    fileNames: list[str]


class BatchDocuments(StrictModel):
    batchId: int | None
    declarationNos: list[str]
    bills: list[Bill]
    planned: list[PlannedContract]
    contracts: list[Contract]
    buyerName: str
    buyerReady: bool
    sellers: list[PartyOption]
    defaults: ContractDefaults
    complete: bool
    issues: list[str]
    warnings: list[str]
    # 批次内各报关单文件（NS 报关资料归档）的现状；未归档只提示
    declarationFiles: list[DeclarationFile]
    edit: Action
    generate: Action
    package: Action
    packageUrl: str
