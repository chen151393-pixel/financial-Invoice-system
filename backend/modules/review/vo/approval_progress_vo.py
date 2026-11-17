"""财务核对与海关回执共用的审核与任务进度。"""

from typing import Literal

from pydantic import Field

from backend.core.dto import StrictModel


class ApprovalStatus(StrictModel):
    status: Literal["approved", "pending", "changed", "blocked"]
    label: str
    reason: str = ""


class ApprovalProgress(StrictModel):
    finance: ApprovalStatus
    customs: ApprovalStatus
    status: Literal[
        "waiting_finance",
        "waiting_customs",
        "waiting_both",
        "missing_receipt",
        "blocked",
        "created",
        "reused",
        "no_task",
        "released",
    ]
    label: str
    reason: str = ""
    nextStep: Literal["finance", "customs", "both", "import", "tasks", "details"]
    linked: bool = False
    taskIds: list[str] = Field(default_factory=list)
