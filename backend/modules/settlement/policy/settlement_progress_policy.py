"""结汇阶段金额分布：每票只进一个阶段；条形比较报关金额，不表示现金未收额。"""

from decimal import Decimal

from .amount_policy import money
from .receivable_policy import STAGE_LABELS
from .route_policy import DIRECT, HK_TRANSIT, ROUTE_LABELS

ZERO = Decimal(0)
STAGES = {
    HK_TRANSIT: ("unregistered", "collected", "remit", "settled"),
    DIRECT: ("unpaid", "partial", "settled"),
}
TONES = {
    "unregistered": "warning",
    "collected": "progress",
    "remit": "info",
    "unpaid": "warning",
    "partial": "progress",
    "settled": "success",
}
NOTES = {
    "unregistered": "尚未登记香港到账",
    "collected": "已登记香港到账，待办理资料",
    "remit": "资料已出，待汇回境内",
    "unpaid": "尚无可冲抵的银行收汇",
    "settled": "该阶段报关金额",
}


def amount(value):
    return str(money(value))


def percent(value, maximum):
    return str((max(ZERO, value) / maximum * 100).quantize(Decimal("0.01"))) if maximum > 0 else "0.00"


def describe(rows):
    usable = [r for r in rows if r["usable"] and r["amount"] >= 0 and r["stage"] in STAGES[r["route"]]]
    result = []
    for currency in sorted({r["currency"] for r in usable}):
        members = [r for r in usable if r["currency"] == currency]
        total = sum((r["amount"] for r in members), ZERO)
        settled = [r for r in members if r["stage"] == "settled"]
        completed = sum((r["amount"] for r in settled), ZERO)
        groups, maximum = [], ZERO
        for route, keys in STAGES.items():
            same = [r for r in members if r["route"] == route]
            stages = []
            for key in keys:
                stage = [r for r in same if r["stage"] == key]
                value = sum((r["amount"] for r in stage), ZERO)
                received = sum((r["received"] for r in stage), ZERO)
                outstanding = sum((r["outstanding"] for r in stage), ZERO)
                maximum = max(maximum, value)
                note = (
                    f"其中已收 {money(received):,.2f} · 未收 {money(outstanding):,.2f}"
                    if key == "partial"
                    else NOTES.get(key, "")
                )
                stages.append(
                    dict(
                        key=key,
                        label=STAGE_LABELS[key],
                        count=len(stage),
                        amount=amount(value),
                        receivedAmount=amount(received),
                        outstandingAmount=amount(outstanding),
                        barWidth="0.00",
                        tone=TONES[key],
                        note=note if stage else "本阶段暂无报关单",
                        select=dict(allowed=bool(stage), reason="" if stage else "本阶段暂无报关单"),
                    )
                )
            groups.append(
                dict(
                    route=route,
                    label=ROUTE_LABELS[route],
                    amount=amount(sum((r["amount"] for r in same), ZERO)),
                    count=len(same),
                    note="香港到账后，汇回境内对平才结汇"
                    if route == HK_TRANSIT
                    else "按客户与收款抬头冲抵，收齐自动结汇",
                    stages=stages,
                )
            )
        for group in groups:
            for stage in group["stages"]:
                stage["barWidth"] = percent(Decimal(stage["amount"]), maximum)
        ratio = percent(completed, total)
        result.append(
            dict(
                currency=currency,
                amount=amount(total),
                count=len(members),
                settledAmount=amount(completed),
                settledCount=len(settled),
                unsettledAmount=amount(total - completed),
                unsettledCount=len(members) - len(settled),
                settledPercent=ratio,
                settledPercentText=f"{Decimal(ratio).quantize(Decimal('0.1'))}%",
                barMaximum=amount(maximum),
                routes=groups,
            )
        )
    return result, len(rows) - len(usable)
