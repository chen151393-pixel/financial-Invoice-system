"""旧待审建议的只读整单预览；不在查询时迁移、确认或改写历史。"""

from backend.modules.invoice.public import read_invoice_paper
from backend.modules.source.public import purchase_order_lines, unit_names
from backend.modules.task.public import open_lines

from ..policy.group_comparison_policy import compare_group
from ..policy.order_group_policy import order_parts
from .group_plan_service import order_contexts


def comparisons(connection, invoice, rows, lines, legacy):
    """按旧建议所选子单的全部有效明细重算；无法完整对应时不沿用旧的一致结论。"""
    if not legacy:
        return {}
    groups = {}
    for row in rows:
        if row["id"] not in legacy:
            continue
        key = ((row["checks"] or {}).get("group") or {}).get("id") or "ungrouped"
        groups.setdefault(key, []).append(row)
    order_ids = sorted(
        {
            lines[row["purchase_line_id"]]["purchase_order_id"]
            for row in rows
            if row["id"] in legacy and row["purchase_line_id"] in lines
        }
    )
    all_lines = purchase_order_lines(connection, order_ids)
    tasks = {row["purchase_line_id"]: row for row in open_lines(connection, [row["id"] for row in all_lines])}
    orders, bases = order_contexts(connection, order_ids, tasks)
    paper = read_invoice_paper(connection, invoice["id"])
    items = [item for item in invoice["items"] if item["is_active"]]
    units, result = unit_names(connection), {}
    for own in groups.values():
        if any(row["purchase_line_id"] not in lines for row in own):
            continue
        selected = {lines[row["purchase_line_id"]]["purchase_order_id"] for row in own}
        parts, context = [], {}
        for order_id in sorted(selected):
            current = orders.get(order_id, {})
            mapped, block = order_parts(invoice, items, current, tasks, bases, units)
            if block:
                break
            parts.extend(mapped)
            context.update(current)
        else:
            if {part["invoice_item_id"] for part in parts} != {item["id"] for item in items}:
                continue
            for item in items:
                expected = [
                    (context[part["purchase_line_id"]], part["quantity"], part["amount"])
                    for part in parts
                    if part["invoice_item_id"] == item["id"]
                ]
                tax = (paper["items"].get(item["id"]) or {}).get("tax_amount")
                compared = compare_group(invoice, item, tax, expected)
                for row in own:
                    if row["invoice_item_id"] == item["id"]:
                        result[row["id"]] = compared
    return result
