"""整单分组规划：发票行对应一张或多张完整子采购单，不拆分子采购明细行。

子采购全部有效明细按综合得分定位发票行，不以品名单项作门槛。完全匹配组合及其他未超出发票容量的
整单候选由 group_plan_service 比较置信度；并列时不猜测归属。建议本身不代表审核通过。
"""

from decimal import Decimal

from .allocation_policy import hard_block, remaining
from .group_comparison_policy import compare_group

# 组合搜索上限：候选单数与搜索节点数；超出时视为无法唯一确定，不自动建议。
MAX_ORDERS = 24
MAX_NODES = 50000


def order_parts(invoice, items, lines, tasks, bases, units):
    """一张子采购单的整单分配 (parts, 阻断原因)；parts 每行为整条明细的剩余应开，按品名对应发票行。

    lines 为 source 门面的子采购行上下文，调用方已补入开票依据的 currency 与 basis_reason。
    """
    parts = []
    for line_id, line in sorted(lines.items()):
        task, basis = tasks.get(line_id), bases.get(line_id)
        block = hard_block(invoice, line, task)
        if block:
            return [], block
        if basis is None or not basis["allowed"] or task["purchase_basis_id"] != basis["id"]:
            return [], "开票依据已变化或未审核"
        if task.get("closed_with_difference"):
            return [], "含已按差异结束的明细"
        quantity, amount = remaining(task)
        if quantity is None or amount is None or quantity < 0 or amount < 0:
            return [], "剩余数量或金额缺失、超开"
        if quantity == 0 and amount == 0:
            continue
        if quantity <= 0 or amount <= 0:
            return [], "明细数量与金额进度不一致"
        # 不一致项只影响得分；同一采购行按综合得分定位发票行，不以品名作准入门槛。
        ranked = [
            (item, compare_group(invoice, item, item.get("tax_amount"), [(line, quantity, amount)])[1])
            for item in items
        ]
        best = max((score for _, score in ranked), default=0)
        matches = [item for item, score in ranked if score == best and score > 0]
        if len(matches) != 1:
            return [], "最高置信度并列或缺少匹配证据，须人工选择发票行"
        item = matches[0]
        parts.append(
            {
                "invoice_item_id": item["id"],
                "purchase_line_id": line_id,
                "purchase_basis_id": basis["id"],
                "quantity": quantity,
                "purchase_quantity": quantity,
                "amount": amount,
            }
        )
    if not parts:
        return [], "子采购单没有剩余应开"
    return parts, ""


def totals(parts):
    """{发票行 ID: (数量合计, 金额合计)}"""
    result = {}
    for part in parts:
        quantity, amount = result.get(part["invoice_item_id"], (Decimal(0), Decimal(0)))
        result[part["invoice_item_id"]] = (quantity + part["quantity"], amount + part["amount"])
    return result


def choose(targets, contributions):
    """在 contributions {子采购单 ID: {发票行 ID: (数量, 金额)}} 中找出合计恰好等于 targets 的组合。

    返回唯一组合的子采购单 ID 列表；没有组合、多于一种组合或超出搜索上限时返回 None。
    """
    orders = sorted(
        (order_id for order_id, own in contributions.items() if set(own) <= set(targets)),
        key=lambda order_id: -sum(amount for _, amount in contributions[order_id].values()),
    )
    if not orders or len(orders) > MAX_ORDERS:
        return None
    found, nodes = [], 0

    def search(index, chosen, sums):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES or len(found) > 1:
            return
        if all(sums.get(key, (0, 0)) == value for key, value in targets.items()):
            found.append(list(chosen))
            return
        if index == len(orders):
            return
        order_id = orders[index]
        merged = dict(sums)
        for key, (quantity, amount) in contributions[order_id].items():
            have_quantity, have_amount = merged.get(key, (Decimal(0), Decimal(0)))
            merged[key] = (have_quantity + quantity, have_amount + amount)
        # 数量与金额都为正数：超出任一发票行即剪枝。
        if all(
            merged[key][0] <= targets[key][0] and merged[key][1] <= targets[key][1]
            for key in contributions[order_id]
        ):
            search(index + 1, chosen + [order_id], merged)
        search(index + 1, chosen, sums)

    search(0, [], {})
    return found[0] if len(found) == 1 and nodes <= MAX_NODES else None


def plan_groups(items, orders, contributions):
    """先求覆盖全部发票行的唯一组合；不成立时逐行求只涉及该行的唯一组合。

    items 为待建议的发票行；orders 为候选子采购单 ID 的优先范围（备注命中优先，已由调用方筛好）。
    返回 [(子采购单 ID 列表, 覆盖的发票行 ID 列表)]，同一子采购单不会出现在两组。
    """
    targets = {
        item["id"]: (item["quantity"], item["amount_including_tax"])
        for item in items
        if item["quantity"] is not None and item["amount_including_tax"] is not None
    }
    candidates = {order_id: contributions[order_id] for order_id in orders if order_id in contributions}
    whole = choose(targets, candidates) if targets else None
    if whole:
        return [(whole, sorted(targets))]
    groups, used = [], set()
    for item_id, target in sorted(targets.items()):
        own = {
            order_id: value
            for order_id, value in candidates.items()
            if order_id not in used and set(value) == {item_id}
        }
        chosen = choose({item_id: target}, own)
        if chosen:
            groups.append((chosen, [item_id]))
            used.update(chosen)
    return groups
