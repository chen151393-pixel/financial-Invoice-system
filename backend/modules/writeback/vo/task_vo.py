"""页面仅展示后端状态和允许动作。"""

from decimal import Decimal

LABELS = {
    "queued": "待匹配账单",
    "waiting_bill": "等待账单",
    "needs_confirmation": "待确认账单",
    "ready": "方案已确认",
    "blocked": "待处理",
    "stale": "审核已失效",
}


def summary(task):
    return {
        "id": str(task["id"]),
        "taskNo": task["task_no"],
        "invoiceId": str(task["invoice_id"]),
        "invoiceNo": task["invoice_no"],
        "vendorName": task["vendor_name"],
        "amount": format(Decimal(task["amount"]), ".2f"),
        "state": task["state"],
        "stateLabel": LABELS[task["state"]],
        "reason": task["reason"],
        "revision": task["revision"],
        "historical": task["historical"],
        "updatedAt": task["updated_at"].isoformat(),
        "writeback": {"allowed": False, "reason": "当前只准备与确认方案，NS 写入尚未接入"},
    }


def detail(task, plan, audit, busy):
    snapshot = task["snapshot"]
    rows = []
    for row in snapshot["allocations"]:
        source = snapshot["sources"][str(row["purchase_line_id"])]
        rows.append(
            {
                "allocationId": str(row["id"]),
                "orderNo": source["order_no"],
                "parentOrderNo": source["parent_number"],
                "parentOrderId": source["parent_id"],
                "amount": format(Decimal(row["amount"]), ".2f"),
            }
        )
    return {
        **summary(task),
        "allocations": rows,
        "invoice": snapshot["invoice"],
        "candidates": task["candidates"],
        "plan": plan["body"] if plan else None,
        "audit": [
            {
                "action": a["action"],
                "actor": a["actor"],
                "detail": a["detail"],
                "at": a["created_at"].isoformat(),
            }
            for a in audit
        ],
        "actions": {
            "refresh": task["state"] != "stale" and not busy,
            "confirm": task["state"] == "needs_confirmation" and not busy,
        },
        "querying": busy,
    }
