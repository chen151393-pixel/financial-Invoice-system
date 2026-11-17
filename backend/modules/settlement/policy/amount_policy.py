"""结汇金额规则（纯函数）：差额只认手续费，到账金额 + 手续费 = 报关金额才算对平。

金额一律 Decimal，按分（两位小数）比较；不使用浮点。
"""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
# 组合推荐的搜索上限：候选过多或节点过多时放弃推荐，由人工勾选。
MAX_SUGGEST_CANDIDATES = 40
MAX_SUGGEST_NODES = 200_000


def cents(value):
    return int((Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP) * 100))


def money(value):
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def difference(declared, arrived, fee):
    """报关金额 −（到账 + 手续费）；正数为少收，负数为多收。"""
    return money(declared) - money(arrived) - money(fee)


def balance_check(declared, arrived, fee, fee_alert):
    """返回 {balanced, difference, warnings}；只做判断，不决定状态。"""
    diff = difference(declared, arrived, fee)
    warnings = []
    if fee is not None and money(fee) > money(fee_alert):
        warnings.append(
            f"手续费 {money(fee)} 超过预警上限 {money(fee_alert)}，请核对银行水单，防止把少收款当作手续费"
        )
    if diff > 0:
        warnings.append(f"到账加手续费比报关金额少 {diff}")
    elif diff < 0:
        warnings.append(f"到账加手续费比报关金额多 {-diff}")
    return {"balanced": diff == 0, "difference": diff, "warnings": warnings}


def suggest_combination(candidates, target):
    """在候选报关单中找金额之和恰好等于 target 的一组。

    candidates: [(报关单号, 金额)]；返回报关单号列表，找不到或超出搜索上限时返回 None。
    """
    goal = cents(target)
    if goal <= 0:
        return None
    pool = [(number, cents(amount)) for number, amount in candidates if 0 < cents(amount) <= goal]
    if not pool or len(pool) > MAX_SUGGEST_CANDIDATES:
        return None
    pool.sort(key=lambda item: item[1], reverse=True)
    suffix = [0] * (len(pool) + 1)
    for index in range(len(pool) - 1, -1, -1):
        suffix[index] = suffix[index + 1] + pool[index][1]
    if suffix[0] < goal:
        return None
    chosen, nodes = [], 0

    def search(index, remaining):
        nonlocal nodes
        nodes += 1
        if remaining == 0:
            return True
        if index >= len(pool) or suffix[index] < remaining or nodes > MAX_SUGGEST_NODES:
            return False
        number, amount = pool[index]
        if amount <= remaining:
            chosen.append(number)
            if search(index + 1, remaining - amount):
                return True
            chosen.pop()
        return search(index + 1, remaining)

    return list(chosen) if search(0, goal) else None
