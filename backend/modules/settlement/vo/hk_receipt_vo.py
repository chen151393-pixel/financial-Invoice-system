"""独立回款登记页响应：核对结果和提交许可均来自后端。"""

from typing import Literal

from backend.core.dto import StrictModel

from .batch_vo import Action
from .hk_workbench_vo import HkPending


class ReceiptCheck(StrictModel):
    key: str
    label: str
    detail: str
    state: Literal["success", "warning", "error"]


class HkRegistrationCheck(StrictModel):
    rows: list[HkPending]
    currency: str
    consignee: str
    declaredTotal: str
    amount: str
    fee: str
    arrivedTotal: str
    difference: str
    balanced: bool
    accounts: list[str]
    checks: list[ReceiptCheck]
    warnings: list[str]
    submit: Action
