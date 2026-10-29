from typing import Annotated, Literal
from uuid import UUID

from backend.core.dto import StrictModel
from pydantic import Field, model_validator

Id = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,18}$")]


class TaskQuery(StrictModel):
    keyword: str = Field(default="", max_length=100)
    taskNo: str = Field(default="", max_length=100)
    invoiceNo: str = Field(default="", max_length=100)
    supplierName: str = Field(default="", max_length=255)
    parentOrderNo: str = Field(default="", max_length=100)
    group: Literal["", "pending", "executing", "applied", "attention", "stale"] = ""
    state: Literal[
        "",
        "queued",
        "waiting_bill",
        "needs_confirmation",
        "needs_preview",
        "ready",
        "executing",
        "applied",
        "conflict",
        "partial",
        "unknown",
        "blocked",
        "stale",
    ] = ""
    page: int = Field(default=1, ge=1, le=100000, strict=False)
    pageSize: int = Field(default=20, ge=1, le=100, strict=False)


class RevisionBody(StrictModel):
    revision: int = Field(ge=1)


class TargetLine(StrictModel):
    allocationId: Id
    billId: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]
    amount: Annotated[str, Field(pattern=r"^(?:0|[1-9][0-9]{0,15})\.[0-9]{2}$")]


class OrderTarget(StrictModel):
    subPurchaseOrderId: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]
    billId: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]


class ConfirmPlan(RevisionBody):
    requestId: UUID = Field(strict=False)
    confirmScope: Literal[True]
    evidence: str = Field(min_length=5, max_length=1000)
    # allocations 保留一个版本兼容旧客户端；两种请求均须满足整单约束。
    allocations: list[TargetLine] | None = Field(default=None, min_length=1, max_length=500)
    orders: list[OrderTarget] | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def one_target_kind(self):
        if (self.orders is None) == (self.allocations is None):
            raise ValueError("须且只能提交 orders 或兼容的 allocations")
        return self


class ConfirmPreview(RevisionBody):
    confirmScope: Literal[True]


class ResolveWrite(RevisionBody):
    # applied：已在 NS 核实登记完整；not_written：已核实 NS 没有任何写入。
    outcome: Literal["applied", "not_written"]
    evidence: str = Field(min_length=5, max_length=1000)
    nsRecordId: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")] | None = None
