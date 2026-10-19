"""按官方网页协议构造的虚构票据，不含真实业务数据。"""

from copy import deepcopy

from backend.tests.sync.test_lemon_invoices import invoice


def full_invoice(**changes):
    raw = invoice(InvoiceType=1170, BusinessType=1, **changes)
    raw["Detail"] = {
        "invoiceId": raw["InvoiceId"],
        "invoiceType": raw["InvoiceType"],
        "number": raw["Number"],
        "code": raw["Code"],
        "invoiceDate": raw["InvoiceDateText"] + "T00:00:00",
        "amount": raw["Amount"],
        "tax": raw["Tax"],
        "name": raw["Name"],
        "isInvalid": raw["IsInvalid"],
        "businessType": raw["BusinessType"],
        "note": raw.get("Note"),
        "invoiceEntries": [
            {
                "name": "墨水",
                "model": "A",
                "unit": "个",
                "quality": "10",
                "amount": raw["Amount"],
                "tax": raw["Tax"],
                "taxRate": "13",
                "sn": 1,
            }
        ],
    }
    return deepcopy(raw)
