"""批量审核按发票返回结果，不以建议条数冒充发票张数。"""

from backend.core.dto import StrictModel


class InvoiceBatchResultItem(StrictModel):
    id: str
    reason: str = ""


class InvoiceBatchResult(StrictModel):
    approved: list[InvoiceBatchResultItem]
    skipped: list[InvoiceBatchResultItem]
