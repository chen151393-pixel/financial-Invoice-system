"""发票行 → 响应对象。"""

from datetime import UTC

from ..vo.invoice_vo import InvoiceDetail, InvoiceLine, InvoiceRow

STATUS_LABELS = {"normal": "正常", "red_offset": "已红冲", "void": "作废", "unknown": "未知"}
SOURCE_LABELS = {"lemon_excel": "Excel导入", "lemon_open2": "柠檬云接口"}


def text(value):
    return format(value, "f") if value is not None else None


def tax_rate(value):
    """0.13 → "13%"；免税、不征税等没有数值税率时为空。"""
    return f"{format((value * 100).normalize(), 'f')}%" if value is not None else None


def row(header, line_count):
    return InvoiceRow(
        id=str(header["id"]),
        number=header["invoice_no"],
        date=header["invoice_date"].isoformat() if header["invoice_date"] else None,
        seller=header["seller_name"],
        sellerTaxNo=header["seller_tax_no"],
        type=header["invoice_type"],
        businessType=header["business_type"],
        status=STATUS_LABELS[header["status"]],
        sourceStatus=header["status"],
        currency=header["currency"],
        net=text(header["amount_excluding_tax"]),
        tax=text(header["tax_amount"]),
        gross=text(header["amount_including_tax"]),
        lineCount=line_count,
        importedAt=header["imported_at"].replace(tzinfo=UTC).isoformat(),
        source=SOURCE_LABELS.get(header["source"], header["source"]),
    )


def line(item):
    return InvoiceLine(
        id=str(item["id"]),
        number=item["line_no"],
        item=item["item_name"],
        specification=item["specification"],
        unit=item["unit"],
        quantity=text(item["quantity"]),
        unitPrice=text(item["unit_price"]),
        net=text(item["amount_excluding_tax"]),
        taxRate=tax_rate(item["tax_rate"]),
        tax=text(item["tax_amount"]),
        gross=text(item["amount_including_tax"]),
    )


def detail(header, item_rows):
    return InvoiceDetail(
        **row(header, len(item_rows)).model_dump(),
        invoiceCode=header["invoice_code"],
        buyer=header["buyer_name"],
        buyerTaxNo=header["buyer_tax_no"],
        remark=header["remark"],
        lines=[line(item) for item in item_rows],
    )
