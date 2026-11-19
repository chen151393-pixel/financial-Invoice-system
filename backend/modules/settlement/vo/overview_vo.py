"""收汇总览响应：金额由后端计算并返回十进制字符串。"""

from typing import Literal

from backend.core.dto import StrictModel

from .ledger_vo import LedgerSkipped


class OverviewAmounts(StrictModel):
    declaredTotal: str
    receivedTotal: str
    outstanding: str
    # 手续费不属于客户实收；按应收减实收计算的未收差额中仍包含手续费。
    receivedFee: str


class OverviewRoute(OverviewAmounts):
    route: Literal["hk_transit", "direct"]
    routeLabel: str


class OverviewTotal(OverviewAmounts):
    currency: str
    routes: list[OverviewRoute]


class OverviewCustomer(OverviewRoute):
    consignee: str
    currency: str
    declarationCount: int


class OverviewList(StrictModel):
    items: list[OverviewCustomer]
    total: int
    page: int
    pageSize: int
    # 合计覆盖全部筛选结果，不受分页影响；不同币种不相加。
    totals: list[OverviewTotal]
    currencies: list[str]
    skipped: list[LedgerSkipped]
