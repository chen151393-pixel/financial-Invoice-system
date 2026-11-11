"""原始报关行缺失时，以子采购报关单位和整组数量定位同名汇总行。"""

from collections import defaultdict
from decimal import Decimal, InvalidOperation


def positive_quantity(raw):
    try:
        quantity = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return quantity if quantity.is_finite() and quantity > 0 else None


def purchase_summary_bindings(groups, summaries, quantities, blocked, diagnostics):
    """先合并同单位全部子行，再精确比较；不拆分采购行、不进行单位换算。"""
    bindings = {}
    for key, rows in groups.items():
        candidates = summaries[key]
        if key in blocked or len(candidates) < 2 or not all(unit for _, unit in candidates):
            continue
        by_unit = defaultdict(list)
        for identity, unit, quantity in rows:
            by_unit[unit].append((identity, positive_quantity(quantity)))
        # 缺失单位的明细无法判断属于哪一组，不能用剩余行凑出某一汇总数量。
        if "" in by_unit:
            continue
        for unit, members in by_unit.items():
            if any(quantity is None for _, quantity in members):
                continue
            total = sum((quantity for _, quantity in members), Decimal(0))
            targets = [
                identity
                for identity, candidate_unit in candidates
                if candidate_unit == unit and positive_quantity(quantities.get(identity)) == total
            ]
            if len(targets) != 1:
                continue
            target = targets[0]
            bindings.update({identity: target for identity, _ in members})
            diagnostics.append(
                {
                    "code": "PURCHASE_SUMMARY_UNIT_QUANTITY",
                    "customsLineId": target,
                    "purchaseLineIds": [identity for identity, _ in members],
                    "purchaseUnitId": unit,
                    "purchaseQuantity": str(total),
                    "message": "按公司、报关品名、货源地、子采购报关单位及汇总数量唯一定位报关明细。",
                }
            )
    return bindings
