"""工作台报表的时间、币种与计数口径；金额仅使用 Decimal。"""

from collections import defaultdict
from datetime import UTC, timedelta, timezone
from decimal import Decimal

BUSINESS_ZONE = timezone(timedelta(hours=8))


def local_date(value):
    return value.replace(tzinfo=UTC).astimezone(BUSINESS_ZONE).date() if value else None


def percent(value, total):
    return format((value / total * 100).quantize(Decimal("0.1")), "f") if total else "0"


def month_report(tasks, today):
    month = today.strftime("%Y-%m")
    cohort = [row for row in tasks if local_date(row["created_at"]).strftime("%Y-%m") == month]
    completed = sum(row["status"] == "completed" for row in cohort)
    received = defaultdict(lambda: Decimal(0))
    for row in cohort:
        received[row["currency"] or ""] += row["received"]
    return {
        "month": month,
        "total": len(cohort),
        "completed": completed,
        "percent": percent(Decimal(completed), Decimal(len(cohort))) if cohort else None,
        "received": [
            {"currency": key, "amount": format(value, "f")} for key, value in sorted(received.items())
        ],
    }


def supplier_ranking(tasks):
    grouped, unknown = defaultdict(lambda: Decimal(0)), set()
    for row in tasks:
        if row["status"] == "completed":
            continue
        key = (row["currency"] or "", row["ns_account"], row["supplier_id"], row["supplier"])
        if row["outstanding"] is None or not row["currency"]:
            unknown.add(key)
        else:
            grouped[key] += row["outstanding"]
    currencies = defaultdict(list)
    for key, amount in grouped.items():
        if key not in unknown and amount > 0:
            currencies[key[0]].append((key, amount))
    result = []
    for currency, values in sorted(currencies.items()):
        top = sorted(values, key=lambda item: (-item[1], item[0][1], str(item[0][2])))[:3]
        for key, amount in top:
            result.append(
                {
                    "currency": currency,
                    "key": f"{key[1]}:{key[2]}:{currency}",
                    "supplier": key[3],
                    "account": key[1],
                    "amount": format(amount, "f"),
                    "percent": percent(amount, top[0][1]),
                }
            )
    return result, len(unknown)


def invoice_trend(rows, today, start=None):
    start = start or today - timedelta(days=6)
    grouped = defaultdict(dict)
    for row in rows:
        if start <= row["date"] <= today:
            grouped[row["currency"] or ""][row["date"]] = row["amount"]
    result = []
    for currency, dates in sorted(grouped.items()):
        maximum = max([abs(value) for value in dates.values() if value is not None] + [Decimal(0)])
        points = []
        # 只展示确有开票记录的日期；零金额或金额待核实的记录仍保留。
        for day, amount in sorted(dates.items()):
            points.append(
                {
                    "date": day.isoformat(),
                    "negative": amount is not None and amount < 0,
                    "amount": format(amount, "f") if amount is not None else None,
                    "percent": percent(abs(amount), maximum) if amount is not None else "0",
                }
            )
        result.append(
            {
                "currency": currency,
                "points": points,
                "hasNegative": any(point["negative"] for point in points),
            }
        )
    return result
