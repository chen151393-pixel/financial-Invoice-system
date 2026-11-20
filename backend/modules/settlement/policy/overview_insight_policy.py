"""总览账龄和待办：复用逐单快照，不把客户已收当成已结汇，不跨币种加总。"""

from decimal import Decimal

from backend.core.names import normalize_name

from .amount_policy import money
from .receivable_policy import SETTLED, STAGE_LABELS, received_percent
from .settlement_progress_policy import percent

ZERO = Decimal(0)
BUCKETS = (("0–30 天", 0, 30), ("31–60 天", 31, 60), ("61–90 天", 61, 90), ("90 天以上", 91, None))


def amount(rows, field="amount"):
    return sum((row[field] for row in rows), ZERO)


def customer_fields(group, rows):
    members = [
        row
        for row in rows
        if row["route"] == group["route"]
        and row["currency"] == group["currency"]
        and normalize_name(row["consignee"]) == normalize_name(group["consignee"])
        and row["usable"]
    ]
    waiting = [row for row in members if row["stage"] != SETTLED]
    dated = [row for row in waiting if row["aging"] is not None]
    oldest = max(dated, key=lambda row: row["aging"]) if dated else None
    width, text = received_percent(group["received"], group["declared"])
    due = group["declared"] - group["received"]
    return {
        "receivedPercent": width,
        "receivedPercentText": text,
        "outstandingTone": "warning" if due > 0 else "info" if due < 0 else "neutral",
        "oldestPendingText": (
            f"{oldest['aging']} 天 · {STAGE_LABELS[oldest['stage']]}"
            if oldest
            else "出口日期待核实"
            if waiting
            else "— · 全部已结汇"
            if members
            else "— · 暂无报关单"
        ),
    }


def _actions(rows, groups, consignee):
    result = []

    def add(key, title, description, value, tone, target, **filters):
        result.append(
            dict(
                key=key,
                title=title,
                description=description,
                amount=str(money(value)),
                tone=tone,
                target=target,
                consignee=consignee,
                **filters,
            )
        )

    overdue = [row for row in rows if row["stage"] == "remit" and row["alert"]]
    if overdue:
        first = max(overdue, key=lambda row: row["aging"] or 0)
        batch = first["batch"]
        batch_no = (batch["batch_no"] or str(batch["id"])) if len(overdue) == 1 else ""
        description = (
            f"{batch_no} · {first['alert']}" if batch_no else f"{len(overdue)} 票超期 · {first['alert']}"
        )
        add("overdue", "香港滞留超期", description, amount(overdue), "danger", "hk", batchNo=batch_no)
    overpaid = [group for group in groups if group["received"] > group["declared"]]
    if overpaid:
        label = overpaid[0]["consignee"] if len(overpaid) == 1 else f"{len(overpaid)} 家客户"
        add(
            "overpaid",
            "客户超收",
            f"{label} · 待核对并在后续报关冲抵",
            sum((g["declared"] - g["received"] for g in overpaid), ZERO),
            "danger",
            "ledger",
        )
    pending = [row for row in rows if row["stage"] == "unregistered"]
    if pending:
        age = max((row["aging"] for row in pending if row["aging"] is not None), default=None)
        note = f" · 最久 {age} 天" if age is not None else " · 出口日期待核实"
        add(
            "register",
            "登记香港回款",
            f"{len(pending)} 票未登记到账{note}",
            amount(pending),
            "warning",
            "receipts",
        )
    missing = [
        row for row in rows if row["stage"] == "collected" and row["document"][0] in ("pending", "stale")
    ]
    if missing:
        batches = {row["batch"]["id"] for row in missing}
        note = missing[0]["document"][1] if len(batches) == 1 else "资料未齐或合同需重新生成"
        add(
            "documents",
            "批次补资料",
            f"{len(batches)} 个批次 · {note}",
            amount(missing),
            "progress",
            "declarations",
            route="hk_transit",
            stage="collected",
        )
    direct = [row for row in rows if row["route"] == "direct" and row["stage"] in ("unpaid", "partial")]
    if direct:
        age = max((row["aging"] for row in direct if row["aging"] is not None), default=None)
        note = f" · 最久 {age} 天" if age is not None else " · 出口日期待核实"
        add(
            "collect",
            "催收直接收汇",
            f"{len(direct)} 票未收齐（逐单推算）{note}",
            amount(direct, "outstanding"),
            "warning",
            "ledger",
        )
    return result


def describe(rows, groups, consignee=""):
    result = []
    usable = [row for row in rows if row["usable"] and row["amount"] >= 0]
    for currency in sorted({row["currency"] for row in usable} | {g["currency"] for g in groups}):
        same = [row for row in usable if row["currency"] == currency]
        pending = [row for row in same if row["stage"] != SETTLED]
        buckets = []
        for label, low, high in BUCKETS:
            members = [
                r
                for r in pending
                if r["aging"] is not None and r["aging"] >= low and (high is None or r["aging"] <= high)
            ]
            buckets.append(
                dict(
                    label=label,
                    amount=str(money(amount(members))),
                    count=len(members),
                    tone="info" if low == 0 else "warning",
                )
            )
        maximum = max((Decimal(bucket["amount"]) for bucket in buckets), default=ZERO)
        for bucket in buckets:
            bucket["barWidth"] = percent(Decimal(bucket["amount"]), maximum)
        same_groups = [group for group in groups if group["currency"] == currency]
        result.append(
            dict(
                currency=currency,
                aging=buckets,
                unsettledAmount=str(money(amount(pending))),
                unsettledCount=len(pending),
                unknownDateCount=sum(r["aging"] is None for r in pending),
                actions=_actions(same, same_groups, consignee),
            )
        )
    return result
