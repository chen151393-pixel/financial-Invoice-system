"""供应商开票时效（纯函数）：通知供应商到发票收齐的天数。

- 通知时间：任务首次进入「等待供应商开票」（awaiting_invoice）；
- 收齐时间：任务首次进入「资料待补齐」或「已完成」（documents_incomplete / completed），即发票已全部收齐；
- 只统计收齐时间在统计窗口内、且收齐晚于通知的任务；按供应商取平均，保留一位小数；
- 超过 SLOW_DAYS 天标为偏慢，供通知时提前催促。
"""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

NOTIFIED = "awaiting_invoice"
RECEIVED = ("documents_incomplete", "completed")
SLOW_DAYS = Decimal(15)
TENTH = Decimal("0.1")


def task_durations(rows, since):
    """rows 为 first_reached 结果；返回 {supplier_id: [天数]}。"""
    by_task = defaultdict(dict)
    supplier = {}
    for row in rows:
        supplier[row["task_id"]] = row["supplier_id"]
        key = "notified" if row["to_status"] == NOTIFIED else "received"
        current = by_task[row["task_id"]].get(key)
        by_task[row["task_id"]][key] = row["at"] if current is None else min(current, row["at"])
    result = defaultdict(list)
    for task_id, times in by_task.items():
        notified, received = times.get("notified"), times.get("received")
        if notified is None or received is None or received < notified or received < since:
            continue
        days = Decimal((received - notified).total_seconds()) / Decimal(86400)
        result[supplier[task_id]].append(days)
    return result


def average(values):
    return (sum(values, Decimal(0)) / len(values)).quantize(TENTH, rounding=ROUND_HALF_UP)
