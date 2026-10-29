"""手动整单关联请求：发票行关联一张完整子采购单，逐条明细的分配数量与含税金额可改小（部分开票）。"""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from backend.core.dto import StrictModel

from .matching_dto import Id, Note


def share(value, label, scale):
    """允许 0：本张发票不开某条明细时，该明细数量与金额同时填 0。"""
    try:
        number = Decimal(str(value))
    except ArithmeticError:
        raise ValueError(f"{label}不是有效数值") from None
    if not number.is_finite() or number < 0 or number >= Decimal(10) ** 16:
        raise ValueError(f"{label}须为范围内的非负数")
    if number != number.quantize(Decimal(1).scaleb(-scale)):
        raise ValueError(f"{label}最多 {scale} 位小数")
    return number


class OrderLineShare(StrictModel):
    purchaseLineId: Id
    quantity: Decimal
    amount: Decimal

    @field_validator("quantity", mode="before")
    @classmethod
    def valid_quantity(cls, value):
        return share(value, "分配数量", 8)

    @field_validator("amount", mode="before")
    @classmethod
    def valid_amount(cls, value):
        return share(value, "分配含税金额", 2)

    @model_validator(mode="after")
    def paired(self):
        if (self.quantity == 0) != (self.amount == 0):
            raise ValueError("同一明细的分配数量与金额须同时为 0 或同时大于 0")
        return self


class ManualOrderBody(StrictModel):
    """lines 须覆盖子采购单当前全部可分配明细（不能只挑部分明细）；可选原子替换同票一条已确认分配。"""

    requestId: UUID = Field(strict=False)
    invoiceId: Id
    invoiceItemId: Id
    purchaseOrderId: Id
    invoiceVersionId: Id | None = None
    lines: list[OrderLineShare] = Field(min_length=1, max_length=200)
    note: Note = ""
    replaceAllocationId: Id | None = None
    replaceReason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""

    @model_validator(mode="after")
    def valid_lines(self):
        ids = [line.purchaseLineId for line in self.lines]
        if len(set(ids)) != len(ids):
            raise ValueError("同一子采购明细不能重复提交")
        if all(line.quantity == 0 for line in self.lines):
            raise ValueError("至少一条明细的分配数量须大于 0")
        if self.replaceAllocationId and not self.replaceReason:
            raise ValueError("替换原关联时请填写替换原因")
        return self
