"""应收看板口径，纯函数，只读。

- 开票月份：任务所关联财务审核记录的通过日期（北京时间）所在月份，不要求通知已发送。
- 回收期限：开票月份的次月最后一天（中国日期）；当天仍算未逾期。
- 已收回：发票全部收齐，即任务进入 资料待补齐 或 已完成；部分收票仍算未收回，金额取未收部分。
- 采购员：供应商 × 采购抬头 的当前负责人（今天已生效的最新版本）；没有负责人为“未指定”。
- 金额：应开金额缺失的任务按件数统计，金额不计入合计，并在 unknown 中给出件数，不以 0 冒充。
"""

from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal

COLLECTED_STATUSES = ("documents_incomplete", "completed")
WINDOW = 4
TOP_SUPPLIERS = 5
OVERDUE_LONG_DAYS = 30
UNASSIGNED = "none"
ZERO = Decimal(0)


def month_of(day):
    return f"{day.year:04d}-{day.month:02d}"


def shift(month, step):
    year, number = int(month[:4]), int(month[5:]) + step
    while number > 12:
        year, number = year + 1, number - 12
    while number < 1:
        year, number = year - 1, number + 12
    return f"{year:04d}-{number:02d}"


def due_date(month):
    following = shift(month, 1)
    year, number = int(following[:4]), int(following[5:])
    return date(year, number, monthrange(year, number)[1])


def default_month(today):
    """本月到期的批次：上个月财务审核通过的任务。"""
    return shift(month_of(today), -1)


def window(today):
    current = month_of(today)
    return [shift(current, step) for step in range(1 - WINDOW, 1)]


def month_label(month):
    return f"{int(month[5:])}月"


def collected(status):
    return status in COLLECTED_STATUSES


def open_amount(row):
    """未收回金额：已收回为 0；未收回取未收部分，应开缺失时为 None。"""
    return ZERO if row["collected"] else row["outstanding"]


def money(value):
    return None if value is None else format(value.quantize(Decimal("0.01")), "f")


def rate(part, whole):
    return round(part * 100 / whole, 1) if whole else None


def total(values):
    known = [value for value in values if value is not None]
    return sum(known, ZERO), len(values) - len(known)


def summary(rows, amount_of):
    amount, unknown = total([amount_of(row) for row in rows])
    return {
        "tasks": len(rows),
        "suppliers": len({row["supplier_id"] for row in rows}),
        "amount": money(amount),
        "unknown": unknown,
    }


def is_overdue(row, today):
    return not row["collected"] and row["due"] < today


def cards(rows, overdue_rows, month, today):
    done = [row for row in rows if row["collected"]]
    pending = [row for row in rows if not row["collected"]]
    expected, unknown = total([row["expected"] for row in rows])
    remaining, _ = total([open_amount(row) for row in rows])
    due = due_date(month) if month != "all" else None
    overdue_months = sorted({row["month"] for row in overdue_rows})
    return {
        "due": summary(rows, lambda row: row["expected"]),
        "collected": {
            **summary(done, lambda row: row["expected"]),
            # 已收回金额 = 应收回 − 未收回，两者合计与应收回一致
            "amount": money(expected - remaining),
            "unknown": unknown,
            "rate": rate(len(done), len(rows)),
        },
        "outstanding": {
            **summary(pending, open_amount),
            "daysLeft": (due - today).days if due else None,
        },
        "overdue": {
            **summary(overdue_rows, open_amount),
            "longOverdue": sum((today - row["due"]).days > OVERDUE_LONG_DAYS for row in overdue_rows),
            "months": [month_label(value) for value in overdue_months],
        },
    }


def months(rows, today):
    current = month_of(today)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["month"]].append(row)
    result = []
    for month in window(today):
        own = grouped[month]
        done = sum(row["collected"] for row in own)
        expected, unknown = total([row["expected"] for row in own])
        remaining, _ = total([open_amount(row) for row in own])
        due = due_date(month)
        result.append(
            {
                "month": month,
                "label": month_label(month),
                "dueDate": due.isoformat(),
                # closed 已过期限；due 本月到期；open 本月审核通过、尚在回收期
                "state": "closed" if due < today else "open" if month == current else "due",
                "tasks": len(own),
                "collected": done,
                "rate": rate(done, len(own)),
                "expected": money(expected),
                "collectedAmount": money(expected - remaining),
                "outstandingAmount": money(remaining),
                "unknown": unknown,
            }
        )
    finished = [item for item in result if item["state"] != "open"]
    tasks = sum(item["tasks"] for item in finished)
    return result, rate(sum(item["collected"] for item in finished), tasks)


def buyers(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["member_key"]].append(row)
    result = [
        {
            "memberId": key,
            "name": own[0]["member_name"] if key != UNASSIGNED else "未指定",
            "tasks": len(own),
            "outstanding": sum(not row["collected"] for row in own),
            "rate": rate(sum(row["collected"] for row in own), len(own)),
        }
        for key, own in grouped.items()
    ]
    # 回收率高的在前，未指定固定最后
    result.sort(key=lambda item: (item["memberId"] == UNASSIGNED, -(item["rate"] or 0), item["name"]))
    return result


def concentration(rows):
    amounts, names = defaultdict(lambda: ZERO), {}
    for row in rows:
        value = open_amount(row)
        if row["collected"] or value is None or value <= 0:
            continue
        amounts[row["supplier_id"]] += value
        names[row["supplier_id"]] = row["supplier"]
    whole = sum(amounts.values(), ZERO)
    ranked = sorted(amounts.items(), key=lambda item: (-item[1], names[item[0]]))
    top, rest = ranked[:TOP_SUPPLIERS], ranked[TOP_SUPPLIERS:]

    def share(value):
        return round(float(value * 100 / whole), 1) if whole else None

    rest_amount = sum((value for _, value in rest), ZERO)
    top_amount = sum((value for _, value in top), ZERO)
    return {
        "amount": money(whole),
        "suppliers": len(ranked),
        "top": [
            {"supplierId": key, "name": names[key], "amount": money(value), "share": share(value)}
            for key, value in top
        ],
        "topAmount": money(top_amount),
        "topShare": share(top_amount),
        "restSuppliers": len(rest),
        "restAmount": money(rest_amount),
        "restShare": share(rest_amount),
    }


def view_rows(rows, overdue_rows, view):
    if view == "overdue":
        return overdue_rows
    if view == "collected":
        return [row for row in rows if row["collected"]]
    if view == "outstanding":
        return [row for row in rows if not row["collected"]]
    return rows


def list_amount(view):
    """清单金额：未收回、逾期看未收部分；应收回、已收回看应开金额。"""
    return open_amount if view in ("outstanding", "overdue") else (lambda row: row["expected"])


def groups(rows, view, today):
    amount_of = list_amount(view)
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["supplier_id"], row["company_id"])].append(row)
    result = []
    for (supplier_id, company_id), own in grouped.items():
        own.sort(key=lambda row: (-(amount_of(row) or ZERO), row["approved_on"], row["id"]))
        amount, unknown = total([amount_of(row) for row in own])
        due = min(row["due"] for row in own)
        result.append(
            {
                "key": f"{supplier_id or 0}-{company_id or 0}",
                "supplierId": supplier_id,
                "supplierName": own[0]["supplier"],
                "companyId": company_id,
                "companyName": own[0]["company"],
                "memberId": own[0]["member_key"],
                "memberName": own[0]["member_name"] if own[0]["member_key"] != UNASSIGNED else "未指定",
                "tasks": len(own),
                "amount": money(amount),
                "unknown": unknown,
                "approvedOn": min(row["approved_on"] for row in own).isoformat(),
                # 旧看板客户端兼容一版本；升级到 approvedOn 后删除此日期别名。
                "notifiedOn": min(row["approved_on"] for row in own).isoformat(),
                "dueDate": due.isoformat(),
                # 未收回才有剩余天数；负数为已逾期天数
                "daysLeft": (due - today).days if any(not row["collected"] for row in own) else None,
                "items": [
                    {
                        "taskId": str(row["id"]),
                        "recordNo": row["record_no"] or "",
                        "orders": row["orders"],
                        "expected": money(row["expected"]),
                        "received": money(row["received"]),
                        "outstanding": money(open_amount(row)),
                        "approvedOn": row["approved_on"].isoformat(),
                        "notifiedOn": row["approved_on"].isoformat(),
                        "dueDate": row["due"].isoformat(),
                        "collected": row["collected"],
                        "node": row["node"],
                        "nodeLabel": row["node_label"],
                    }
                    for row in own
                ],
                "_amount": amount,
            }
        )
    result.sort(key=lambda item: (-item["_amount"], item["supplierName"], item["key"]))
    for item in result:
        del item["_amount"]
    return result


def matches(row, query, terms, orders):
    if query.memberId and row["member_key"] != query.memberId:
        return False
    if query.companyId and str(row["company_id"]) != query.companyId:
        return False
    if terms and not any(term in row["supplier"].casefold() for term in terms):
        return False
    if orders:
        numbers = [row["record_no"] or "", *row["orders"]]
        if not any(term in number.casefold() for term in orders for number in numbers):
            return False
    return True
