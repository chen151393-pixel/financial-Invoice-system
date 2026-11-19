"""直接收汇报关资料列表，不包含或改变客户收款状态。"""

from backend.core.dto import StrictModel

from .batch_vo import Action


class DirectDocumentRow(StrictModel):
    declarationNo: str
    recordNo: str
    salesOrders: list[str]
    consignee: str
    exportCompany: str
    currency: str
    amount: str
    billLabel: str
    contractLabel: str
    status: str
    statusLabel: str
    edit: Action


class DirectDocumentList(StrictModel):
    items: list[DirectDocumentRow]
    total: int
    page: int
    pageSize: int
