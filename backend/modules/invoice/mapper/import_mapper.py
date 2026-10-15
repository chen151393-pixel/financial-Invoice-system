"""Excel 解析结果 → 新表行；只做转换与列约束校验，不访问数据库。"""

import hashlib
import json
from decimal import Decimal

from backend.core.errors import ApiError
from backend.core.names import normalize_name

from ..entity import headers, items

EXCEL_SOURCE = "lemon_excel"
# Excel 导入暂用固定账套标识；接入柠檬云 open2 时与 API 账套对齐，按 invoice_key 识别同一张票。
EXCEL_ACCOUNT = "lemon"
CENT = Decimal("0.01")


def invoice_key(code, number):
    """发票代码 + 号码（数电票代码为空）。"""
    return f"{code or ''}:{number}"


def json_safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def raw_payload(document):
    """原始票头与明细（不含文件名、工作表行号），同一张票在不同文件中得到相同摘要。"""
    return json_safe(
        {
            "head": document["rawHead"]["values"],
            "lines": sorted(
                (line["values"] for line in document["rawLines"]),
                key=lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, default=str),
            ),
            "contentHash": document["head"]["content_hash"],
        }
    )


def payload_digest(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def cents(value, label):
    if value is None:
        return None
    if value != value.quantize(CENT):
        raise ApiError(422, f"{label}超过两位小数，不符合发票金额精度")
    return value


def checked(table, values, number):
    for key, value in values.items():
        length = getattr(table.c[key].type, "length", None)
        if isinstance(value, str) and length and len(value) > length:
            raise ApiError(422, f"发票{number}字段{key}超过数据库长度{length}")
    return values


def header_values(document, raw_record_id, now):
    head, number = document["head"], document["head"]["invoice_no"]
    label = f"发票{number}"
    values = {
        "source": EXCEL_SOURCE,
        "lemon_account": EXCEL_ACCOUNT,
        "invoice_code": head.get("invoice_code") or None,
        "invoice_no": number,
        "invoice_key": invoice_key(head.get("invoice_code"), number),
        "invoice_date": head["invoice_date"],
        "invoice_type": head.get("invoice_type_name"),
        "business_type": head.get("business_type_name"),
        "status": head["invoice_status"],
        "seller_name": head.get("seller_name"),
        "seller_name_normalized": normalize_name(head.get("seller_name"))[:255] or None,
        "seller_tax_no": head.get("seller_tax_no"),
        # 柠檬云 Excel 不含购买方；比对时购买方一项记为发票未提供。
        "buyer_name": None,
        "buyer_name_normalized": None,
        "buyer_tax_no": None,
        "currency": "CNY",
        "amount_excluding_tax": cents(head["amount_excluding_tax"], label),
        "tax_amount": cents(head["tax_amount"], label),
        "amount_including_tax": cents(head["amount_including_tax"], label),
        "remark": head.get("remark"),
        "raw_record_id": raw_record_id,
        "imported_at": now,
    }
    return checked(headers, values, number)


def item_values(document):
    number = document["head"]["invoice_no"]
    label = f"发票{number}明细"
    result = []
    for line in document["lines"]:
        values = {
            "source_line_key": line["source_line_key"],
            "line_no": line["line_no"],
            "item_name": line["item_name"],
            "item_name_normalized": normalize_name(line["item_name"])[:500] or None,
            "specification": line.get("specification"),
            "quantity": line.get("quantity"),
            "unit": line.get("unit_name"),
            "unit_price": None,
            "amount_excluding_tax": cents(line["amount_excluding_tax"], label),
            "tax_rate": line.get("tax_rate"),
            "tax_amount": cents(line["tax_amount"], label),
            "amount_including_tax": cents(line["amount_including_tax"], label),
        }
        result.append(checked(items, values, number))
    return result
