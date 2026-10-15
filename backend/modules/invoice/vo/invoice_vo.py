"""发票列表与详情响应：金额为十进制字符串，主键为字符串。"""

from backend.core.dto import StrictModel


class InvoiceRow(StrictModel):
    id: str
    number: str
    date: str | None
    seller: str | None
    sellerTaxNo: str | None
    type: str | None
    businessType: str | None
    status: str
    sourceStatus: str
    currency: str
    net: str | None
    tax: str | None
    gross: str | None
    lineCount: int
    importedAt: str
    source: str


class AmountSummary(StrictModel):
    currency: str
    count: int
    net: str | None
    tax: str | None
    gross: str | None


class InvoiceList(StrictModel):
    total: int
    page: int
    pageSize: int
    hasPrevious: bool
    hasNext: bool
    rows: list[InvoiceRow]
    amounts: list[AmountSummary]


class InvoiceLine(StrictModel):
    id: str
    number: str | None
    item: str | None
    specification: str | None
    unit: str | None
    quantity: str | None
    unitPrice: str | None
    net: str | None
    taxRate: str | None
    tax: str | None
    gross: str | None


class InvoiceDetail(InvoiceRow):
    invoiceCode: str | None
    buyer: str | None
    buyerTaxNo: str | None
    remark: str | None
    lines: list[InvoiceLine]
