"""发票业务内容摘要与逻辑明细身份；显示行号不是身份。"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

HEADER_FIELDS = (
    "invoice_code",
    "invoice_no",
    "invoice_date",
    "invoice_type",
    "business_type",
    "status",
    "seller_name",
    "seller_tax_no",
    "buyer_name",
    "buyer_tax_no",
    "currency",
    "amount_excluding_tax",
    "tax_amount",
    "amount_including_tax",
    "remark",
    "detail_status",
)
ITEM_FIELDS = (
    "item_name",
    "specification",
    "quantity",
    "unit",
    "unit_price",
    "amount_excluding_tax",
    "tax_rate",
    "tax_amount",
    "amount_including_tax",
)


def safe(value):
    if isinstance(value, dict):
        return {k: safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [safe(v) for v in value]
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value else "0"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def identity(item):
    return tuple(item.get(k) or "" for k in ("item_name", "specification", "unit"))


def digest(header, items):
    head = {k: header.get(k) for k in HEADER_FIELDS}
    head["detail_status"] = header.get("detail_status", "complete")
    rows = [safe({k: r.get(k) for k in ITEM_FIELDS}) for r in items if r.get("is_active", True)]
    payload = [safe(head), sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def ambiguous(old, new):
    left, right = [identity(r) for r in old if r["is_active"]], [identity(r) for r in new]
    return len(left) != len(set(left)) or len(right) != len(set(right))


def projection(header, rows, old):
    """预估与保存共用完整性规则，避免待补齐或歧义票反复产生相同版本。"""
    head = dict(header)
    if not rows or head.get("detail_status", "complete") != "complete":
        head["detail_status"] = "pending"
        return head, old
    if ambiguous(old, rows):
        head["detail_status"] = "failed"
        return head, old
    head["detail_status"] = "complete"
    return head, rows
