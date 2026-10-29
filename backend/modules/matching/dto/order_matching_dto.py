"""整张子采购单候选与原子确认请求。数量换算由后端预览，提交绑定同一预览摘要。"""

from uuid import UUID

from pydantic import Field

from .matching_dto import ConversionBody, Id, Note


class OrderCandidateQuery(ConversionBody):
    invoiceId: Id
    keyword: str = Field(default="", max_length=100)
    page: int = Field(default=1, ge=1, le=100000)
    pageSize: int = Field(default=10, ge=1, le=50)


class OrderConfirmBody(ConversionBody):
    requestId: UUID = Field(strict=False)
    invoiceId: Id
    purchaseOrderId: Id
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    note: Note = ""
