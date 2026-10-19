"""当前筛选全部发票的统计；金额按币种分组，以十进制字符串传输。"""

from backend.core.dto import StrictModel


class InvoiceCurrencyTotals(StrictModel):
    currency: str
    count: int
    gross: str | None
    tax: str | None
    pendingAmount: str
    pendingCount: int
    reviewAmount: str
    reviewCount: int


class InvoiceTotals(StrictModel):
    amounts: list[InvoiceCurrencyTotals]
