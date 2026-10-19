"""跟进列表的金额进度与等待口径；只读计算，不改变任务完成条件。"""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal


def amounts(lines):
    # 任一应开值缺失时不以部分金额冒充完整进度；零或负总额不能作百分比分母。
    if not lines or any(line["expected_amount"] is None for line in lines):
        return None, None, None
    expected = sum((line["expected_amount"] for line in lines), Decimal(0))
    received = sum((line["received_amount"] for line in lines), Decimal(0))
    # 一行超收不能抵消另一行欠收；已结束与被替代行不再列入待收。
    outstanding = sum(
        (
            max(Decimal(0), line["expected_amount"] - line["received_amount"])
            for line in lines
            if line["status"] in ("open", "partial")
        ),
        Decimal(0),
    )
    percent = (
        (received / expected * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if expected > 0 else None
    )
    return outstanding, percent, min(Decimal(100), max(Decimal(0), percent)) if percent is not None else None


def waiting(task, now):
    if task["status"] == "completed":
        return "已完成"
    if task["status"] == "superseded":
        return "已被替代"
    created = task["created_at"]
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    days = max(0, (now - created).days)
    return f"已等待 {days} 天"


def fields(task, lines, contact=None, *, now=None):
    outstanding, percent, bar = amounts(lines)
    return {
        "outstandingAmount": format(outstanding, "f") if outstanding is not None else None,
        "receiptPercent": format(percent.normalize(), "f") if percent is not None else None,
        "receiptBarPercent": format(bar.normalize(), "f") if bar is not None else None,
        "followupEmployee": (contact or {}).get("sender_name") or "",
        "lastContactAt": contact["sent_at"].replace(tzinfo=UTC).isoformat() if contact else None,
        "waitingLabel": waiting(task, now or datetime.now(UTC)),
    }
