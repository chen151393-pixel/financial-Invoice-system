"""由冻结方案生成发送 NS 的正文与逐账单预览；不访问数据库和外部系统。"""

import re
from collections import defaultdict
from decimal import Decimal

from backend.core.errors import ApiError

MAX_BILLS = 20


def money(value):
    return format(Decimal(value), ".2f")


def build(task, targets, candidates, request_id):
    invoice = task["snapshot"]["invoice"]
    number, date = invoice["invoice_no"], str(invoice["invoice_date"])[:10]
    if not number or len(number) > 100 or number != number.strip():
        raise ApiError(409, "发票号码不能作为 NS 发票记录名称，需专项处理")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ApiError(409, "开票日期格式无法写入 NS")
    bills = {bill["billId"]: bill for order in candidates["purchaseOrders"] for bill in order["bills"]}
    amounts, orders = defaultdict(Decimal), {}
    for target in targets:
        amounts[target["billId"]] += Decimal(target["amount"])
        orders.setdefault(target["billId"], set()).add(target["purchaseOrderId"])
    if len(amounts) > MAX_BILLS:
        raise ApiError(409, f"一张发票涉及账单超过 {MAX_BILLS} 张，需专项处理")
    if any(len(found) != 1 for found in orders.values()):
        raise ApiError(409, "同一账单对应了多个母采购，不能写入")
    total = sum(amounts.values(), Decimal(0))
    if money(total) != money(invoice["amount_including_tax"]):
        raise ApiError(409, "账单分配合计与发票含税金额不一致")
    lines, preview = [], []
    for bill_id in sorted(amounts, key=int):
        bill, amount = bills[bill_id], amounts[bill_id]
        before = Decimal(bill["amounts"]["received"])
        lines.append(
            {
                "billId": bill_id,
                "purchaseOrderId": next(iter(orders[bill_id])),
                "amount": money(amount),
                "expectedBefore": money(before),
            }
        )
        # 写后累计 = 写前累计 ＋ 本次金额；累计与明细的历史差额原样保留，只展示给财务确认。
        preview.append(
            {
                "billId": bill_id,
                "billNumber": bill["billNumber"],
                "purchaseOrderId": bill["purchaseOrderId"],
                "before": money(before),
                "amount": money(amount),
                "after": money(before + amount),
                "available": money(bill["amounts"]["available"]),
                "detailsTotal": money(bill["details"]["total"]),
                "difference": money(before - Decimal(bill["details"]["total"])),
                "consistent": bill["consistent"],
            }
        )
    payload = {
        "action": "apply",
        "requestId": request_id,
        "vendorId": task["vendor_id"],
        "invoice": {"number": number, "date": date, "amount": money(total)},
        "bills": lines,
    }
    return payload, preview, any(not line["consistent"] for line in preview)
