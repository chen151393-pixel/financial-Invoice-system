"""工作台报表的时间、币种与计数口径；金额仅使用 Decimal。"""

from collections import defaultdict
from datetime import UTC, timedelta, timezone
from decimal import Decimal

BUSINESS_ZONE = timezone(timedelta(hours=8))


def local_date(value):
    return value.replace(tzinfo=UTC).astimezone(BUSINESS_ZONE).date() if value else None


def percent(value, total):
    return format((value / total * 100).quantize(Decimal("0.1")), "f") if total else "0"


def month_of(value):
    """UTC 时间 → 北京时间所在月份 YYYY-MM。"""
    return local_date(value).strftime("%Y-%m")


def expected_month(task):
    """应开归属关联报关单的 NS 创建月份；缺失时不回退到任务生成日期。"""
    created = task.get("declaration_created_at")
    return month_of(created) if created else None


def month_keys(today, months=6):
    """截至 today 所在月的最近 months 个月（升序）。"""
    keys = []
    year, month = today.year, today.month
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return keys[::-1]


# 供应商最长等待天数超过该值时提示（橙色）
OVERDUE_DAYS = 15


def supplier_ranking(tasks, limit=6):
    """未完成任务按 供应商 × 账套 × 币种 汇总待收金额，每个币种取前 limit 名，人民币在前。

    金额或币种不完整的分组不参与排名（不以部分金额冒充），只返回组数；最长等待取该组未完成任务中最早生成的天数。
    """
    grouped, unknown = defaultdict(lambda: Decimal(0)), set()
    longest = defaultdict(int)
    for row in tasks:
        if row["status"] == "completed":
            continue
        key = (row["currency"] or "", row["ns_account"], row["supplier_id"], row["supplier"])
        longest[key] = max(longest[key], row["waiting_days"] or 0)
        if row["outstanding"] is None or not row["currency"]:
            unknown.add(key)
        else:
            grouped[key] += row["outstanding"]
    currencies = defaultdict(list)
    for key, amount in grouped.items():
        if key not in unknown and amount > 0:
            currencies[key[0]].append((key, amount))
    result = []
    for currency, values in sorted(currencies.items(), key=lambda item: (item[0] != "CNY", item[0])):
        top = sorted(values, key=lambda item: (-item[1], item[0][1], str(item[0][2])))[:limit]
        for key, amount in top:
            result.append(
                {
                    "currency": currency,
                    "key": f"{key[1]}:{key[2]}:{currency}",
                    "supplier": key[3],
                    "account": key[1],
                    "amount": format(amount, "f"),
                    "percent": percent(amount, top[0][1]),
                    "longestDays": longest[key],
                    "overdue": longest[key] > OVERDUE_DAYS,
                }
            )
    return result, len(unknown)


def monthly_receipts(tasks, receipts, today, months=6, currency="CNY"):
    """应开按关联报关单 NS 创建月，收票按全部正常人民币进项票的开票月（含未匹配）。

    receipts 来自 invoice 门面的按日期汇总；比值不表示同一批任务完成率，可超过 100%。
    应开缺失只影响应开统计，不影响独立的票面收票金额。
    """
    keys = month_keys(today, months)
    expected = dict.fromkeys(keys, Decimal(0))
    received = dict.fromkeys(keys, Decimal(0))
    invoice_counts = dict.fromkeys(keys, 0)
    unknown = dict.fromkeys(keys, 0)
    for row in tasks:
        key = expected_month(row)
        if key not in expected or (row["currency"] or "") != currency:
            continue
        if row["expected"] is None:
            unknown[key] += 1
            continue
        expected[key] += row["expected"]
    for row in receipts:
        key = row["date"].strftime("%Y-%m")
        if key in received:
            received[key] += Decimal(str(row["gross"] or 0))
            invoice_counts[key] += row["count"]
    return [
        {
            "month": key,
            "currency": currency,
            "expected": format(expected[key], "f"),
            "received": format(received[key], "f"),
            "invoiceCount": invoice_counts[key],
            "percent": percent(received[key], expected[key]) if expected[key] else None,
            "unknownTasks": unknown[key],
        }
        for key in keys
    ]
