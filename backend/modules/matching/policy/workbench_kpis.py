"""工作台关键指标（纯函数）：数值、对比说明与近 6 个月序列都在这里算好，前端只展示。

应开与待收来自人民币任务；收票金额来自按开票月份归集的全部正常人民币进项票（含未匹配）。
"""

from decimal import Decimal

from .workbench_reports import OVERDUE_DAYS, expected_month, month_keys, month_of


def _delta(text, direction="flat", tone="neutral"):
    return {"delta": text, "direction": direction, "tone": tone}


def _month_change(current, previous):
    """较上月变化；上月为 0 时不给百分比。"""
    if not previous:
        return _delta("上月无应开金额")
    change = (current - previous) / previous * 100
    sign = "+" if change > 0 else ""
    return _delta(
        f"较上月 {sign}{format(change.quantize(Decimal('0.1')), 'f')}%",
        "up" if change > 0 else "down" if change < 0 else "flat",
    )


def _counts_by_month(keys, values):
    found = dict.fromkeys(keys, 0)
    for key in values:
        if key in found:
            found[key] += 1
    return [str(found[key]) for key in keys]


def kpis(*, monthly, tasks, reviews, today):
    """monthly：monthly_receipts 结果；tasks：账套范围内的当前任务；reviews：范围内待财务审核的报关单。"""
    keys = month_keys(today, len(monthly))
    current, previous = monthly[-1], monthly[-2] if len(monthly) > 1 else None
    cny = [row for row in tasks if row["currency"] == "CNY"]
    this_month = [row for row in cny if expected_month(row) == keys[-1]]
    open_cny = [row for row in cny if row["status"] != "completed"]
    known = [row for row in open_cny if row["outstanding"] is not None]
    outstanding_by_month = dict.fromkeys(keys, Decimal(0))
    for row in known:
        key = month_of(row["created_at"])
        if key in outstanding_by_month:
            outstanding_by_month[key] += row["outstanding"]
    longest = max((row["waiting_days"] or 0 for row in open_cny), default=0)
    suppliers = {(row["ns_account"], row["supplier_id"]) for row in known if row["outstanding"] > 0}
    unknown = len(open_cny) - len(known)
    changed = sum(bool(row.get("changed")) for row in reviews)
    notify = [row for row in tasks if row["node"] == "notification"]
    documents = sum(row["node"] == "documents" for row in tasks)
    return [
        {
            "key": "expected",
            "label": "本月应开金额",
            "role": "finance",
            "value": current["expected"],
            "unit": "",
            "currency": "CNY",
            **_month_change(
                Decimal(current["expected"]), Decimal(previous["expected"]) if previous else None
            ),
            "hint": f"本月创建报关单关联 {len(this_month)} 个开票任务",
            "series": [item["expected"] for item in monthly],
        },
        {
            "key": "received",
            "label": "本月收票金额",
            "role": "finance",
            "value": current["received"],
            "unit": "",
            "currency": "CNY",
            **_delta(
                f"收票／应开比 {current['percent']}%" if current["percent"] is not None else "本月暂无应开",
                tone="positive" if current["percent"] is not None else "neutral",
            ),
            "hint": f"本月开票 {current['invoiceCount']} 张正常进项票（含未匹配）",
            "series": [item["received"] for item in monthly],
        },
        {
            "key": "outstanding",
            "label": "待收金额",
            "role": "finance",
            "value": format(sum((row["outstanding"] for row in known), Decimal(0)), "f"),
            "unit": "",
            "currency": "CNY",
            **_delta(
                f"最长已等 {longest} 天" if open_cny else "没有未完成任务",
                tone="warning" if longest > OVERDUE_DAYS else "neutral",
            ),
            "hint": f"涉及 {len(suppliers)} 家供应商"
            + (f"，另有 {unknown} 个任务金额待核实" if unknown else ""),
            "series": [format(outstanding_by_month[key], "f") for key in keys],
        },
        {
            "key": "review",
            "label": "待财务审核",
            "role": "finance",
            "value": str(len(reviews)),
            "unit": "张",
            "currency": "",
            **_delta(
                f"{changed} 张来源变化需重审" if changed else "无来源变化",
                tone="warning" if changed else "neutral",
            ),
            "hint": "报关单待财务核对",
            "series": _counts_by_month(
                keys, (month_of(row["ns_created_at"]) for row in reviews if row.get("ns_created_at"))
            ),
        },
        {
            "key": "notify",
            "label": "待通知供应商",
            "role": "purchase",
            "value": str(len(notify)),
            "unit": "个",
            "currency": "",
            **_delta(
                f"另有 {documents} 个待存合同" if documents else "合同均已归档",
                tone="warning" if documents else "neutral",
            ),
            "hint": "合同已归档，可通知供应商开票",
            "series": _counts_by_month(keys, (month_of(row["created_at"]) for row in notify)),
        },
    ]
