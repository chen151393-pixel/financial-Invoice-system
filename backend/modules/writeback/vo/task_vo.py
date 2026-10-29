"""页面仅展示后端状态和允许动作。"""

from decimal import Decimal

from ..policy.state_policy import WRITTEN_STATES, stuck

LABELS = {
    "queued": "待匹配账单",
    "waiting_bill": "等待账单",
    "needs_confirmation": "待确认账单",
    "needs_preview": "待确认回写预览",
    "ready": "待写入 NS",
    "executing": "正在写入 NS",
    "applied": "NS 已登记",
    "conflict": "NS 已有同号登记",
    "partial": "部分写入，待核实",
    "unknown": "结果不明，待核实",
    "blocked": "待处理",
    "stale": "审核已失效",
}


def writeback(task, gate):
    if task["state"] == "applied":
        return {"allowed": False, "reason": "NS 已登记"}
    if task["state"] != "ready":
        return {"allowed": False, "reason": LABELS[task["state"]]}
    allowed, reason = gate.check(task)
    return {"allowed": allowed, "reason": reason}


def summary(task, gate):
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
        "writeback": writeback(task, gate),
    }


def iso(value):
    return value.isoformat() if value else None


def request_view(request):
    if not request:
        return None
    return {
        "requestId": request["request_id"],
        "state": request["state"],
        "invoice": request["payload"]["invoice"],
        "preview": request["preview"],
        "needsConfirmation": request["needs_confirmation"],
        "confirmedBy": request["confirmed_by"],
        "confirmedAt": iso(request["confirmed_at"]),
        "nsRecordId": request["ns_record_id"],
        "sentAt": iso(request["sent_at"]),
        "finishedAt": iso(request["finished_at"]),
    }


def detail(task, plan, request, audit, busy, gate, stamp):
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
    halted = stuck(task, request, stamp)
    return {
        **summary(task, gate),
        "allocations": rows,
        "invoice": snapshot["invoice"],
        "candidates": task["candidates"],
        "plan": plan["body"] if plan else None,
        "request": request_view(request),
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
            "refresh": task["state"] not in ("stale", *WRITTEN_STATES) and not busy,
            "confirm": task["state"] == "needs_confirmation" and not busy,
            "confirmPreview": task["state"] == "needs_preview" and not busy,
            "execute": writeback(task, gate)["allowed"] and not busy,
            "resolve": task["state"] in ("unknown", "partial") or halted,
            "markNotWritten": task["state"] == "unknown" or halted,
        },
        "querying": busy,
    }
