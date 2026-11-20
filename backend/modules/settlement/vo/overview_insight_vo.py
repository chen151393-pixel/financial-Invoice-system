"""收汇总览账龄及下一步：金额、几何宽度和业务状态由后端给出。"""

from typing import Literal

from backend.core.dto import StrictModel


class OverviewAging(StrictModel):
    label: str
    amount: str
    count: int
    barWidth: str
    tone: Literal["info", "warning"]


class OverviewAction(StrictModel):
    key: str
    title: str
    description: str
    amount: str
    tone: Literal["danger", "warning", "progress", "info"]
    target: Literal["declarations", "hk", "receipts", "ledger"]
    route: str = "all"
    stage: str = "all"
    consignee: str = ""
    batchNo: str = ""


class OverviewInsight(StrictModel):
    currency: str
    aging: list[OverviewAging]
    unsettledAmount: str
    unsettledCount: int
    unknownDateCount: int
    actions: list[OverviewAction]
