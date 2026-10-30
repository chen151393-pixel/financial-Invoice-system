"""为一张发票规划整单建议：召回候选子采购单，经各模块只读门面取上下文，再按 order_group_policy 选组合。"""

from backend.modules.invoice.public import read_invoice_paper
from backend.modules.review.public import current_bases
from backend.modules.source.public import purchase_lines, purchase_order_lines, unit_names

from ..policy.comparison_policy import order_reference, supplier_result
from ..policy.group_comparison_policy import compare_group
from ..policy.order_group_policy import fit_all, order_parts, plan_groups, totals


def recall_orders(invoice, task_contexts):
    """单号命中及供应商相近的子单共同召回，由综合评分决定默认建议。"""
    by_remark, by_supplier = set(), set()
    for line in task_contexts.values():
        if order_reference(invoice["remark"], line):
            by_remark.add(line["purchase_order_id"])
        elif supplier_result(invoice["seller_name"], line["supplier_name"]) in ("match", "partial"):
            by_supplier.add(line["purchase_order_id"])
    return sorted(by_remark | by_supplier)


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
    combinations = plan_groups(items, order_ids, contributions)
    exact_count = len(combinations)
    # 单张子采购单覆盖整张发票全部行时，数量或金额有差异（发票多或少）也保留为候选，评分后默认展示最高分；
    # 差异须在审核时填写说明，发票少的明细确认时按差异结束。
    alternatives = [
        ([order_id], sorted(own))
        for order_id, own in contributions.items()
        if set(own) == set(by_item) and all(by_item[key]["quantity"] is not None for key in own)
    ]
    combinations.extend(candidate for candidate in alternatives if candidate not in combinations)
    for chosen, item_ids in combinations:
        rows = fit_all(
            [
                part
                for order_id in chosen
                for part in parts_by_order[order_id]
                if part["invoice_item_id"] in item_ids
            ],
            by_item,
        )
        lines = {line_id: line for order_id in chosen for line_id, line in grouped[order_id].items()}
        checks = {}
        for item_id in item_ids:
            # 比对口径是子采购整单应开，不是压缩后的记账数
            own = [
                (lines[row["purchase_line_id"]], row["share_quantity"], row["share_amount"])
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
    if not result:
        return []
    options = ([result[:exact_count]] if exact_count else []) + [[group] for group in result[exact_count:]]
    scores = [min(score for group in option for _, score in group["checks"].values()) for option in options]
    best = max(scores)
    # 同分不能靠数据库顺序决定账务归属，保留人工选择。
    return options[scores.index(best)] if best > 0 and scores.count(best) == 1 else []
