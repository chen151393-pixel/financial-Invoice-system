"""子采购单是回写分配单位；原审核明细保留用于金额守恒和追溯。"""

from decimal import Decimal

from backend.core.errors import ApiError


def order_groups(task):
    snapshot, groups = task["snapshot"], {}
    for row in snapshot["allocations"]:
        source = snapshot["sources"][str(row["purchase_line_id"])]
        key = source["subpo_id"]
        group = groups.setdefault(key, {"source": source, "rows": [], "amount": Decimal(0)})
        group["rows"].append(row)
        group["amount"] += Decimal(row["amount"])
    return groups


def expand_orders(task, targets):
    groups, selected, expanded = order_groups(task), {}, []
    for target in targets:
        key = target["subPurchaseOrderId"]
        if key not in groups:
            raise ApiError(409, "子采购单不属于当前审核快照")
        if key in selected:
            raise ApiError(422, "同一子采购单只能分配一次，不能拆分到账单")
        selected[key] = target["billId"]
    if set(selected) != set(groups):
        raise ApiError(422, "必须为每张子采购单选择目标账单")
    for key, group in groups.items():
        expanded.extend(
            {
                "allocationId": str(row["id"]),
                "billId": selected[key],
                "amount": format(Decimal(row["amount"]), ".2f"),
            }
            for row in group["rows"]
        )
    return expanded


def require_whole_orders(task, targets):
    """兼容旧客户端明细请求，但不再允许拆分子采购单或变更审核金额。"""
    rows = {str(row["id"]): row for row in task["snapshot"]["allocations"]}
    seen, chosen = set(), {}
    for target in targets:
        key = target["allocationId"]
        row = rows.get(key)
        if row is None:
            raise ApiError(409, "分配不属于当前审核快照")
        if key in seen or Decimal(target["amount"]) != Decimal(row["amount"]):
            raise ApiError(422, "子采购单须整单分配，不能拆分或修改明细金额")
        seen.add(key)
        source = task["snapshot"]["sources"][str(row["purchase_line_id"])]
        order_id = source["subpo_id"]
        if chosen.setdefault(order_id, target["billId"]) != target["billId"]:
            raise ApiError(422, "同一子采购单须分配到同一账单，不能按商品明细拆分")
    if seen != set(rows):
        raise ApiError(422, "子采购单须完整分配全部审核明细")
