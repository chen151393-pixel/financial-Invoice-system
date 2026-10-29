"""为一张发票规划整单建议：召回候选子采购单，经各模块只读门面取上下文，再按 order_group_policy 选组合。"""

from backend.modules.invoice.public import read_invoice_paper
from backend.modules.review.public import current_bases
from backend.modules.source.public import purchase_lines, purchase_order_lines, unit_names

from ..policy.comparison_policy import order_reference, supplier_result
from ..policy.group_comparison_policy import compare_group
from ..policy.order_group_policy import order_parts, plan_groups, totals


def recall_orders(invoice, task_contexts):
    """备注命中子单或母单的子采购单优先；都未命中时按供应商模糊匹配召回。"""
    by_remark, by_supplier = set(), set()
    for line in task_contexts.values():
        if order_reference(invoice["remark"], line):
            by_remark.add(line["purchase_order_id"])
        elif supplier_result(invoice["seller_name"], line["supplier_name"]) in ("match", "partial"):
            by_supplier.add(line["purchase_order_id"])
    return sorted(by_remark or by_supplier)


def order_contexts(connection, order_ids, tasks):
    """{子采购单 ID: {子采购行 ID: 上下文}}，覆盖整单全部有效来源行（不只是有任务的行）。"""
    rows = purchase_order_lines(connection, order_ids)
    contexts = purchase_lines(connection, [row["id"] for row in rows])
    bases = current_bases(connection, list(contexts))
    grouped = {}
    for line_id, line in contexts.items():
        basis = bases.get(line_id)
        line.update(
            currency=basis["currency"] if basis else None,
            basis_reason=basis["reason"] if basis else "缺少有效开票依据",
            basis_id=basis["id"] if basis else None,
        )
        grouped.setdefault(line["purchase_order_id"], {})[line_id] = line
    return grouped, bases


def plan(connection, invoice, items, task_lines):
    """返回 [{"orderIds", "itemIds", "rows": [分配行], "checks": {发票行 ID: (checks, confidence)}}]。"""
    tasks = {row["purchase_line_id"]: row for row in task_lines}
    task_contexts = purchase_lines(connection, list(tasks))
    order_ids = recall_orders(invoice, task_contexts)
    if not order_ids or not items:
        return []
    grouped, bases = order_contexts(connection, order_ids, tasks)
    units = unit_names(connection)
    parts_by_order = {}
    for order_id, lines in grouped.items():
        parts, block = order_parts(invoice, items, lines, tasks, bases, units)
        if not block:
            parts_by_order[order_id] = parts
    contributions = {order_id: totals(parts) for order_id, parts in parts_by_order.items()}
    paper = read_invoice_paper(connection, invoice["id"]) or {"items": {}}
    by_item = {item["id"]: item for item in items}
    result = []
    for chosen, item_ids in plan_groups(items, order_ids, contributions):
        rows = [
            part
            for order_id in chosen
            for part in parts_by_order[order_id]
            if part["invoice_item_id"] in item_ids
        ]
        lines = {line_id: line for order_id in chosen for line_id, line in grouped[order_id].items()}
        checks = {}
        for item_id in item_ids:
            own = [
                (lines[row["purchase_line_id"]], row["purchase_quantity"], row["amount"])
                for row in rows
                if row["invoice_item_id"] == item_id
            ]
            face = paper["items"].get(item_id, {})
            checks[item_id] = compare_group(invoice, by_item[item_id], face.get("tax_amount"), own)
        result.append(
            {
                "orderIds": [str(order_id) for order_id in chosen],
                "itemIds": item_ids,
                "rows": rows,
                "lines": lines,
                "checks": checks,
            }
        )
    return result
