"""按子采购单汇总展示审核和冻结方案，不修改保存的历史正文。"""

from decimal import Decimal

from ..policy.order_policy import order_groups


def orders(task):
    bills = [
        bill for parent in (task["candidates"] or {}).get("purchaseOrders", []) for bill in parent["bills"]
    ]
    result = []
    for key, group in order_groups(task).items():
        source = group["source"]
        result.append(
            {
                "subPurchaseOrderId": key,
                "orderNo": source["order_no"],
                "parentOrderNo": source["parent_number"],
                "parentOrderId": source["parent_id"],
                "amount": format(group["amount"], ".2f"),
                "lineCount": len({row["purchase_line_id"] for row in group["rows"]}),
                "allocations": [
                    {
                        "allocationId": str(row["id"]),
                        "purchaseLineId": str(row["purchase_line_id"]),
                        "amount": format(Decimal(row["amount"]), ".2f"),
                    }
                    for row in group["rows"]
                ],
                "eligibleBillIds": [
                    bill["billId"]
                    for bill in bills
                    if bill["purchaseOrderId"] == source["parent_id"]
                    and bill["vendorId"] == source["vendor_id"]
                    and bill["currencyId"] == source["currency_id"]
                    and (not bill["subPurchaseOrderId"] or bill["subPurchaseOrderId"] == key)
                ],
            }
        )
    return result


def plan_view(task, plan):
    if not plan:
        return None
    indexed = {str(row["id"]): group for group in order_groups(task).values() for row in group["rows"]}
    grouped = {}
    for target in plan["body"]["allocations"]:
        source = indexed[target["allocationId"]]["source"]
        key = (source["subpo_id"], target["billId"])
        row = grouped.setdefault(
            key,
            {
                "subPurchaseOrderId": key[0],
                "orderNo": source["order_no"],
                "billId": key[1],
                "amount": Decimal(0),
            },
        )
        row["amount"] += Decimal(target["amount"])
    return {
        **plan["body"],
        "orders": [{**row, "amount": format(row["amount"], ".2f")} for row in grouped.values()],
    }
