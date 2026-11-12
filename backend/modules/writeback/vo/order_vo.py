"""按子采购单汇总展示审核和冻结方案，不修改保存的历史正文。"""

from decimal import Decimal

from ..policy.order_policy import order_groups


def parent_orders(task):
    # 沿用任务创建时冻结的来源身份，重复商品和多个子采购单不重复展示同一母单。
    parents = {}
    for source in (task["snapshot"].get("sources") or {}).values():
        parent_id = str(source.get("parent_id") or "")
        number = str(source.get("parent_number") or "")
        if parent_id or number:
            parents.setdefault((parent_id, number), {"id": parent_id, "number": number})
    return list(parents.values())


def _labels(task):
    """NS 内部 ID → 业务名称。母单号以本次 NS 查询结果为准；子采购单号取任务冻结的审核快照。

    子公司名称优先取 NS 查询返回的 subsidiaryName；旧查询结果没有该字段时，才用审核快照中“subsidiary:<ID>”身份的公司名称。
    """
    sources = (task["snapshot"].get("sources") or {}).values()
    parents = {
        str(s["parent_id"]): s["parent_number"]
        for s in sources
        if s.get("parent_id") and s.get("parent_number")
    }
    subpos = {str(s["subpo_id"]): s["order_no"] for s in sources if s.get("subpo_id") and s.get("order_no")}
    companies = {}
    for source in sources:
        # 只有“subsidiary:<ID>”身份才对应 NS 子公司；分类等其他身份不能当作子公司名称
        kind, _, ns_id = (source.get("company_ns_id") or "").partition(":")
        if kind == "subsidiary" and source.get("company_name"):
            companies[ns_id] = source["company_name"]
    for order in (task["candidates"] or {}).get("purchaseOrders", []):
        if order.get("number"):
            parents[str(order["id"])] = order["number"]
    return parents, subpos, companies


def candidates_view(task):
    """候选账单附带母采购单号、子采购单号与子公司名称，页面不再展示 NS 内部 ID；取不到时为空串。"""
    result = task["candidates"]
    if not result:
        return result
    parents, subpos, companies = _labels(task)

    def label(bill):
        return {
            **bill,
            "purchaseOrderNo": parents.get(bill["purchaseOrderId"], ""),
            "subPurchaseOrderNo": subpos.get(bill["subPurchaseOrderId"], ""),
            "subsidiaryName": bill.get("subsidiaryName") or companies.get(bill["subsidiaryId"], ""),
        }

    return {
        **result,
        "purchaseOrders": [
            {**order, "bills": [label(bill) for bill in order["bills"]]} for order in result["purchaseOrders"]
        ],
    }


def preview_view(task, preview):
    """回写预览保存的是 NS 母单 ID，展示时补母采购单号，不修改已冻结的预览正文。"""
    parents = _labels(task)[0]
    return [{**row, "purchaseOrderNo": parents.get(row["purchaseOrderId"], "")} for row in preview]


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


def plan_view(task, plan, names=None):
    if not plan:
        return None
    indexed = {str(row["id"]): group for group in order_groups(task).values() for row in group["rows"]}
    numbers = {
        bill["billId"]: bill["billNumber"]
        for parent in (task["candidates"] or {}).get("purchaseOrders", [])
        for bill in parent["bills"]
    }
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
                "billNumber": numbers.get(key[1], ""),
                "amount": Decimal(0),
            },
        )
        row["amount"] += Decimal(target["amount"])
    confirmed_by = plan["body"].get("confirmedBy", "")
    return {
        **plan["body"],
        "confirmedByName": (names or {}).get(confirmed_by, confirmed_by),
        "orders": [{**row, "amount": format(row["amount"], ".2f")} for row in grouped.values()],
    }
