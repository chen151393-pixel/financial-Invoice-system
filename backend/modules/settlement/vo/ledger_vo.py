"""直接收汇明细（总账）响应：总账差额、状态与合计均由服务器计算；金额为十进制字符串。"""

from typing import Literal

from backend.core.dto import StrictModel

LedgerStatus = Literal["outstanding", "settled", "overpaid"]


class LedgerEntry(StrictModel):
    kind: Literal["export", "receipt"]
    kindLabel: str
    # 出口行填写出口抬头、日期、金额；收汇行填写收汇抬头、日期、金额；另一侧为空串
    exportCompany: str
    exportDate: str
    exportAmount: str
    receiptCompany: str
    receiptDate: str
    receiptAmount: str
    # 来源单据：出口为报关单号，收汇为银行流水号
    sourceNo: str
    # 该组计入本笔后的累计余额
    balance: str
    thirdParty: bool
    payerName: str


class LedgerGroup(StrictModel):
    consignee: str
    receivingCompany: str = ""
    openingBalance: str = "0.00"
    currency: str
    exportTotal: str
    receiptTotal: str
    balance: str
    status: LedgerStatus
    statusLabel: str
    entries: list[LedgerEntry]


class LedgerTotal(StrictModel):
    currency: str
    openingBalance: str = "0.00"
    exportTotal: str
    receiptTotal: str
    balance: str
    # 余额为正的收货人合计（未收）与余额为负的收货人合计（超收，负数）
    outstanding: str
    overpaid: str
    consigneeCount: int
    exportCount: int
    receiptCount: int


class LedgerSkipped(StrictModel):
    declarationNo: str
    consignee: str
    reason: str


class LedgerList(StrictModel):
    groups: list[LedgerGroup]
    # 符合筛选的境外收货人（按币种分开）总数
    total: int
    page: int
    pageSize: int
    # 筛选范围内各币种合计（不受分页影响）
    totals: list[LedgerTotal]
    # 未计入总账的直接收汇报关单（金额或币制有问题、没有境外收货人）
    skipped: list[LedgerSkipped]
