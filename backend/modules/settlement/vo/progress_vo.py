"""结汇阶段金额图：金额、占比和共同比较刻度由后端提供。"""

from backend.core.dto import StrictModel

from .batch_vo import Action


class ProgressStage(StrictModel):
    key: str
    label: str
    count: int
    amount: str
    receivedAmount: str
    outstandingAmount: str
    barWidth: str
    tone: str
    note: str
    select: Action


class ProgressRoute(StrictModel):
    route: str
    label: str
    amount: str
    count: int
    note: str
    stages: list[ProgressStage]


class ProgressCurrency(StrictModel):
    currency: str
    amount: str
    count: int
    settledAmount: str
    settledCount: int
    unsettledAmount: str
    unsettledCount: int
    settledPercent: str
    settledPercentText: str
    barMaximum: str
    routes: list[ProgressRoute]


class SettlementProgress(StrictModel):
    currencies: list[ProgressCurrency]
    excludedCount: int
    asOf: str
