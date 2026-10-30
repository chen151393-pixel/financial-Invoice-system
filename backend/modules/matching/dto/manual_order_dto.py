"""手动整单关联请求：发票关联一张完整子采购单；各明细记账数量与金额由后端按整单与发票生成，不接受前端填写。"""

from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from backend.core.dto import StrictModel

from .matching_dto import Id, Note


class ManualOrderBody(StrictModel):
    """一张子采购单只由一张发票开具：整单关联，可选原子替换同票一条已确认分配。"""

    requestId: UUID = Field(strict=False)
    invoiceId: Id
    invoiceItemId: Id
    purchaseOrderId: Id
    invoiceVersionId: Id | None = None
    note: Note = ""
    replaceAllocationId: Id | None = None
    replaceReason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""

    @model_validator(mode="after")
    def valid_replace(self):
        if self.replaceAllocationId and not self.replaceReason:
            raise ValueError("替换原关联时请填写替换原因")
        return self
