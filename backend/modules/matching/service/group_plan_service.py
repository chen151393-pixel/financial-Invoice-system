"""为一张发票规划整单建议：召回候选子采购单，经各模块只读门面取上下文，再按 order_group_policy 选组合。"""

from backend.modules.invoice.public import read_invoice_paper
from backend.modules.review.public import current_bases
from backend.modules.source.public import purchase_lines, purchase_order_lines, unit_names

from ..policy.comparison_policy import order_reference, remark_purchase_numbers, supplier_result
from ..policy.group_comparison_policy import compare_group
from ..policy.order_group_policy import fit_all, order_parts, plan_groups, totals

# 按供应商召回（备注无可识别单号）时的最低门槛：销售方与供应商一致，或整单综合分不低于此值
SUPPLIER_RECALL_MIN_SCORE = 50
# 按供应商召回时，每个发票行至少须有一项硬指标与整单一致（2026-11-25）
HARD_EVIDENCE = ("quantity", "amount")


def recall_orders(invoice, task_contexts):
    """返回 (子采购单 ID 列表, 召回方式)。

    - remark：备注中的可识别单号（子 / 母采购单号，或可分配子单关联的销售订单号）命中可分配子单，只在命中范围内比对；
    - missing：备注写了我方采购单号，但没有命中任何可分配子单（未入库、未审核或已不可分配），不按供应商找替代单；
    - supplier：备注没有可识别单号，按销售方与供应商名称召回，生成建议还须有硬指标（has_hard_evidence）
      并过 SUPPLIER_RECALL_MIN_SCORE 门槛。
    """
    by_remark, by_supplier = set(), set()
    for line in task_contexts.values():
        if order_reference(invoice["remark"], line):
            by_remark.add(line["purchase_order_id"])
        elif supplier_result(invoice["seller_name"], line["supplier_name"]) in ("match", "partial"):
            by_supplier.add(line["purchase_order_id"])
    if by_remark:
        return sorted(by_remark), "remark"
    if remark_purchase_numbers(invoice["remark"]):
        return [], "missing"
    return sorted(by_supplier), "supplier"


def seller_matched(option):
    """组合内全部发票行的销售方比对均为一致。"""
    return all(
        check["result"] == "match"
        for group in option
        for checks, _ in group["checks"].values()
        for check in checks
        if check["key"] == "seller"
    )


def has_hard_evidence(option):
    """组合内每个发票行的数量或含税金额至少一项与整单一致。

    只有供应商、品名、单位一致时，同供应商任意一张同品名开放子采购单都能凑到 45 分，
    多是发票对应的单尚未生成任务时的误猜，不作为建议。
    """
    return all(
        any(check["key"] in HARD_EVIDENCE and check["result"] == "match" for check in checks)
        for group in option
        for checks, _ in group["checks"].values()
    )


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
    order_ids, mode = recall_orders(invoice, task_contexts)
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
    if best <= 0 or scores.count(best) != 1:
        return []
    chosen = options[scores.index(best)]
    if mode == "supplier" and not has_hard_evidence(chosen):
        # 备注无单号，数量和金额又都对不上，只凭供应商与品名猜的单不作为建议（仍可人工关联）
        return []
    if mode == "supplier" and best < SUPPLIER_RECALL_MIN_SCORE and not seller_matched(chosen):
        # 备注无单号时按供应商猜的单，销售方又不一致且分数低，不作为建议（仍可手动关联）
        return []
    return chosen
