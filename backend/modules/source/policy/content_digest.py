"""报关单展示内容摘要：报关单 + 报关明细 + 有效关联的子采购单与明细 + 关联关系。

审核通过时保存摘要；来源再次同步后摘要变化，即表示需要重新审核。只使用 NS 身份与业务字段，
不使用本地自增 ID 或同步时间，同样的来源内容总是得到同样的摘要。
"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

DECLARATION_FIELDS = ("ns_internal_id", "record_no", "declaration_no", "declaration_date", "declarant_name")
CUSTOMS_LINE_FIELDS = (
    "source_line_key",
    "line_no",
    "pl_no",
    "sales_order_no",
    "company_name",
    "origin_place",
    "item_code",
    "declaration_name",
    "specification",
    "quantity",
    "unit",
    "declared_quantity",
    "declared_unit",
    "unit_price",
    "amount",
    "currency",
)
ORDER_FIELDS = (
    "ns_internal_id",
    "order_no",
    "order_date",
    "pl_no",
    "parent_order_no",
    "supplier_name",
    "company_name",
    "currency",
    "total_amount",
)
LINE_FIELDS = (
    "source_line_key",
    "line_no",
    "item_code",
    "item_name",
    "declaration_name",
    "specification",
    "quantity",
    "unit",
    "declared_quantity",
    "declared_unit",
    "unit_price",
    "amount",
    "amount_status",
)


def canonical(value):
    if isinstance(value, Decimal):
        # 统一小数表示：数据库按列精度补零，比较时只看数值。
        return format(value.normalize(), "f") if value else "0"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def pick(row, fields):
    return {name: canonical(row.get(name)) for name in fields}


def content_digest(declaration, customs_lines, orders, lines, links):
    """declaration、customs_lines 等为数据库读出的行（dict）；links 只含有效关联。"""
    order_keys = {order["id"]: order["ns_internal_id"] for order in orders}
    customs_keys = {line["id"]: line["source_line_key"] for line in customs_lines}
    line_keys = {
        line["id"]: (order_keys[line["purchase_order_id"]], line["source_line_key"]) for line in lines
    }
    content = {
        "declaration": pick(declaration, DECLARATION_FIELDS),
        "customsLines": sorted(
            (pick(line, CUSTOMS_LINE_FIELDS) for line in customs_lines), key=lambda r: r["source_line_key"]
        ),
        "orders": sorted((pick(order, ORDER_FIELDS) for order in orders), key=lambda r: r["ns_internal_id"]),
        "lines": sorted(
            ({"order": order_keys[line["purchase_order_id"]], **pick(line, LINE_FIELDS)} for line in lines),
            key=lambda r: (r["order"], r["source_line_key"]),
        ),
        "links": sorted(
            [
                order_keys[link["purchase_order_id"]],
                customs_keys.get(link["customs_line_id"]) or "",
                "/".join(line_keys[link["purchase_line_id"]]) if link["purchase_line_id"] else "",
                link["evidence"],
            ]
            for link in links
        ),
    }
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()
