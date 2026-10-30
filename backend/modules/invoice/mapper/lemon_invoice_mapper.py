"""官方票头转换为 invoice 当前投影；人民币来源规则与 Excel 一致。"""

from backend.core.names import normalize_name

from ..entity import headers
from .import_mapper import checked, invoice_key, json_safe, payload_digest
from .lemon_detail_mapper import item_values


def prepare(raw, values, account, detail_rows=(), detail_status="pending", account_name=""):
    seller = raw.get("Name") or None
    # 上游进项票不含购买方；进项票属于账套所属公司，按柠檬云账套名称填写（用户 2026-10-29 确认）。
    buyer = account_name.strip()[:255] or None
    header = {
        "source": "lemon_professional" if account.startswith("professional:") else "lemon_open2",
        "lemon_account": account,
        "external_id": str(raw["InvoiceId"]),
        "invoice_code": raw.get("Code") or None,
        "invoice_no": raw["Number"],
        "invoice_key": invoice_key(raw.get("Code"), raw["Number"]),
        "invoice_date": values["date"],
        "invoice_type": raw.get("InvoiceTypeText"),
        "business_type": values["business"],
        "status": values["status"],
        "seller_name": seller,
        "seller_name_normalized": normalize_name(seller)[:255] or None,
        "seller_tax_no": raw.get("TaxpayerNumber"),
        "buyer_name": buyer,
        "buyer_name_normalized": normalize_name(buyer)[:255] or None,
        "buyer_tax_no": None,
        "currency": "CNY",
        "amount_excluding_tax": values["net"],
        "tax_amount": values["tax"],
        "amount_including_tax": values["gross"],
        "remark": raw.get("Note"),
        "detail_status": detail_status,
    }
    checked(headers, header, raw["Number"])
    payload = json_safe(raw)
    return {
        "header": header,
        "rows": item_values(detail_rows, raw["Number"]),
        "key": header["invoice_key"],
        "payload": payload,
        "digest": payload_digest(payload),
    }
