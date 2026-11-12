"""按当前页所见的发票版本和完整建议集合批量审核，一次最多 50 张。"""

from pydantic import Field, model_validator

from backend.core.dto import StrictModel

from .matching_dto import Id, Note


class InvoiceBatchItem(StrictModel):
    invoiceId: Id
    invoiceVersionId: Id
    allocationIds: list[Id] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def unique_allocations(self):
        if len(set(self.allocationIds)) != len(self.allocationIds):
            raise ValueError("同一发票的建议不能重复")
        return self


class InvoiceBatchBody(StrictModel):
    items: list[InvoiceBatchItem] = Field(min_length=1, max_length=50)
    note: Note = ""

    @model_validator(mode="after")
    def unique_invoices(self):
        ids = [item.invoiceId for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("同一发票不能重复提交")
        return self
