"""银行收汇明细响应：三方代付标记与去向由服务器给出；金额为十进制字符串。"""

from backend.core.dto import StrictModel

from .batch_vo import Route


class BankReceipt(StrictModel):
    id: int
    receiptDate: str
    receiptTime: str
    receivingCompany: str
    receivingAccount: str
    payerName: str
    # 实际客户，即境外收货人（取导入表格）
    customerName: str
    # 付款人户名与实际客户不同
    thirdParty: bool
    currency: str
    amount: str
    reference: str
    # 实际客户的回款路径：直接收汇进直接收汇明细；香港中转在批次登记汇回，不进总账
    route: Route
    routeLabel: str


class BankReceiptTotal(StrictModel):
    receivingCompany: str
    currency: str
    count: int
    amount: str
    thirdPartyCount: int
    thirdPartyAmount: str


class BankReceiptList(StrictModel):
    items: list[BankReceipt]
    total: int
    page: int
    pageSize: int
    # 筛选范围内按收汇抬头与币种汇总（不受分页影响）
    totals: list[BankReceiptTotal]


class BankReceiptImportResult(StrictModel):
    imported: int
    duplicates: int
    ignored: int
