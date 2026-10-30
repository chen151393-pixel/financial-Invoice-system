"""整单分组规划：整张发票对应一张或多张完整子采购单，不拆分子采购明细行（2026-10-30 业务规则）。

- 一张子采购单只由一张发票开具：已有收票（含待复核占用）的子采购单不能再关联其他发票。
- 子采购全部有效明细按综合得分定位发票行，不以品名单项作门槛；组合必须覆盖整张发票。
- 发票少于子采购单时按明细顺序记到发票为止，差额在确认时按差异结束；发票多时明细记满应开。
建议本身不代表审核通过；并列时不猜测归属。
"""

from decimal import Decimal

from .allocation_policy import hard_block
from .group_comparison_policy import compare_group

ONE_INVOICE = "子采购单已关联其他发票；一张子采购单只能由一张发票开具，开少的请按差异结束"
# 组合搜索上限：候选单数与搜索节点数；超出时视为无法唯一确定，不自动建议。
MAX_ORDERS = 24
MAX_NODES = 50000


def taken(task):
    """任务行已有收票、待复核占用或已结束：一张子采购单只能由一张发票开具，不能再关联其他发票。"""
    return task["status"] not in ("open", "partial") or any(
        task.get(key)
        for key in ("received_quantity", "received_amount", "pending_quantity", "pending_amount")
    )


def order_shares(invoice, lines, tasks, bases):
    """一张子采购单各明细的整单应开 ({子采购行 ID: (数量, 金额)}, 阻断原因)。

    整单是最小单位：任一明细不在有效应开范围、依据变化、已有收票或已结束时整单不可分配。
    lines 为 source 门面的子采购行上下文，调用方已补入开票依据的 currency 与 basis_reason。
    """
    shares = {}
    for line_id, line in sorted(lines.items()):
        task, basis = tasks.get(line_id), bases.get(line_id)
        block = hard_block(invoice, line, task)
        if block:
            return {}, block
        if basis is None or not basis["allowed"] or task["purchase_basis_id"] != basis["id"]:
            return {}, "开票依据已变化或未审核"
        if taken(task):
            return {}, ONE_INVOICE
        quantity, amount = task["expected_quantity"], task["expected_amount"]
        if quantity is None or amount is None or quantity <= 0 or amount <= 0:
            return {}, "明细应开数量或金额缺失"
        shares[line_id] = (quantity, amount)
    if not shares:
        return {}, "子采购单没有有效明细"
    return shares, ""


def order_parts(invoice, items, lines, tasks, bases, units):
    """一张子采购单的整单分配 (parts, 阻断原因)；parts 每行为整条明细的剩余应开，按品名对应发票行。"""
    shares, block = order_shares(invoice, lines, tasks, bases)
    if block:
        return [], block
    parts = []
    for line_id, (quantity, amount) in shares.items():
        line, basis = lines[line_id], bases[line_id]
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
    return parts, ""


def fit(parts, item):
    """把对应同一发票行的明细按顺序记到发票行数量、金额为止；返回新列表，不改原行。

    每行保留 share_quantity / share_amount（子采购整单应开）供比对；记少于应开的明细在确认时按差异结束。
    发票数量或金额缺失时不压缩，交由比对项提示。
    """
    left_quantity, left_amount = item.get("quantity"), item.get("amount_including_tax")
    result = []
    for part in parts:
        share_quantity, share_amount = part["quantity"], part["amount"]
        quantity, amount = share_quantity, share_amount
        if left_quantity is not None and left_amount is not None:
            quantity = min(share_quantity, max(left_quantity, Decimal(0)))
            amount = min(share_amount, max(left_amount, Decimal(0)))
            left_quantity, left_amount = left_quantity - quantity, left_amount - amount
        result.append(
            {
                **part,
                "quantity": quantity,
                "purchase_quantity": quantity,
                "amount": amount,
                "share_quantity": share_quantity,
                "share_amount": share_amount,
            }
        )
    return result


def share_snapshot(row):
    """保存到分配 checks.orderShare 的整单应开（十进制文本）。"""
    return {"quantity": str(row["share_quantity"]), "amount": str(row["share_amount"])}


def order_share(allocation):
    """(整单应开数量, 金额)；没有快照的历史分配取分配本身。"""
    share = (allocation["checks"] or {}).get("orderShare")
    if not share:
        return allocation["quantity"], allocation["amount"]
    return Decimal(share["quantity"]), Decimal(share["amount"])


def short_lines(allocations):
    """记账少于整单应开的分配（发票少）；确认时这些子采购明细按差异结束。"""
    result = []
    for row in allocations:
        if (row["checks"] or {}).get("orderShare"):
            quantity, amount = order_share(row)
            if row["quantity"] < quantity or row["amount"] < amount:
                result.append(row)
    return result


def fit_all(parts, items):
    """按发票行分别 fit；items 为 {发票行 ID: 发票行}。"""
    result = []
    for item_id in dict.fromkeys(part["invoice_item_id"] for part in parts):
        own = [part for part in parts if part["invoice_item_id"] == item_id]
        result.extend(fit(own, items[item_id]))
    return result


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
    """求覆盖整张发票全部行、数量与金额恰好相等的唯一组合。

    items 为待建议的发票行；orders 为候选子采购单 ID 的优先范围（已由调用方筛好）。
    返回 [(子采购单 ID 列表, 覆盖的发票行 ID 列表)]；不再按单行拆出部分组合。
    """
    targets = {
        item["id"]: (item["quantity"], item["amount_including_tax"])
        for item in items
        if item["quantity"] is not None and item["amount_including_tax"] is not None
    }
    if not targets or len(targets) != len(items):
        return []
    candidates = {order_id: contributions[order_id] for order_id in orders if order_id in contributions}
    whole = choose(targets, candidates)
    return [(whole, sorted(targets))] if whole else []
