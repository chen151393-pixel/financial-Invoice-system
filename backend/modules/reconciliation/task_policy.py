"""从不可变审核范围拆分任务，不以整单采购金额推导可开票额度。"""

import hashlib
import json


def key(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def text(value):
    return str(value).strip() if value is not None else ""


def split_scope(payload, account, declaration_id):
    """稳定身份缺失时隔离到子采购单，不能凭同名供应商/公司跨单合并。"""
    if payload.get("source") == "database":
        content = payload["content"]
        orders = content["purchases"]
        lines = content["purchaseLines"]
    else:
        # 兼容NS展示契约不含供应商/采购公司内部身份，保留逐行依据待人工补齐。
        orders_by_number, lines = {}, []
        for row in payload["group"]["rows"]:
            if row["side"] != "purchase":
                continue
            cells = row["cells"]
            identity = cells[5] or row["sourceKey"] or row["id"]
            orders_by_number.setdefault(
                identity,
                {
                    "id": identity,
                    "order_no": cells[5],
                    "supplier_name": cells[7],
                    "currency_code": row.get("currency", ""),
                },
            )
            lines.append(
                {
                    "id": row["sourceKey"] or row["id"],
                    "purchase_order_id": identity,
                    "declaration_name": cells[9],
                    "quantity": cells[11],
                    "unit_name": cells[12],
                    "amount": cells[14],
                }
            )
        orders = list(orders_by_number.values())
    groups = {}
    for order in orders:
        order_id = order["id"]
        supplier_id = text(order.get("supplier_identifier"))
        company_id = text(order.get("company_identifier"))
        currency = text(order.get("currency_code"))
        supplier_key = (
            key(account, "supplier", supplier_id) if supplier_id else key(account, "order", order_id)
        )
        company_key = company_id or f"unknown-order:{order_id}"
        group_key = key(supplier_key, company_key, currency or f"unknown-order:{order_id}")
        if group_key not in groups:
            reasons = []
            if not supplier_id:
                reasons.append("缺少供应商身份标识，暂按子采购单隔离，不能仅凭名称合并。")
            if not company_id:
                reasons.append("缺少采购公司身份标识，不能用申报公司代替开票购方。")
            if not currency:
                reasons.append("来源未提供币种，以采购订单原件为准；不影响资料下载。")
            groups[group_key] = {
                "group_key": group_key,
                "supplier_key": supplier_key,
                "declaration_key": key(account, declaration_id),
                "supplier": text(order.get("supplier_name")) or "供应商待确认",
                "company": text(order.get("company_name")) or "采购公司待确认",
                "currency": currency,
                "payload": {"orders": [], "lines": [], "reasons": reasons},
            }
        scoped = groups[group_key]["payload"]
        scoped["orders"].append({"id": str(order_id), "number": text(order.get("order_no"))})
        scoped["lines"].extend(
            {
                "id": str(line["id"]),
                "order": text(order.get("order_no")),
                "name": text(line.get("declaration_name") or line.get("item_name")),
                "quantity": text(line.get("quantity")),
                "unit": text(line.get("unit_name")),
                "amount": text(line.get("amount")),
                "currency": currency,
            }
            for line in lines
            if line["purchase_order_id"] == order_id
        )
    return list(groups.values())
