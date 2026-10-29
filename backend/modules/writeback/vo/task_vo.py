"""页面仅展示后端状态和允许动作。"""

from decimal import Decimal

from backend.core.errors import ApiError

from ..policy.list_policy import GROUP_STATES
from ..policy.order_policy import require_whole_orders
from ..policy.state_policy import WRITTEN_STATES, stuck
from .order_vo import orders, parent_orders, plan_view

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


def state_options(by_state):
    groups = {state: group for group, states in GROUP_STATES.items() for state in states}
    return [
        {"state": state, "label": label, "group": groups[state], "count": by_state.get(state, 0)}
        for state, label in LABELS.items()
    ]


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
        "parentOrders": parent_orders(task),
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
    capability = writeback(task, gate)
    plan_issue = ""
    if plan and task["state"] in ("ready", "needs_preview"):
        try:
            require_whole_orders(task, plan["body"]["allocations"])
        except ApiError:
            plan_issue = "历史方案按明细拆分了子采购单，请重新查询账单并按整单确认"
            capability = {"allowed": False, "reason": plan_issue}
    return {
        **summary(task, gate),
        "writeback": capability,
        "reason": plan_issue or task["reason"],
        "allocations": rows,
        "orders": orders(task),
        "invoice": snapshot["invoice"],
        "candidates": task["candidates"],
        "plan": plan_view(task, plan),
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
            "confirmPreview": task["state"] == "needs_preview" and not busy and not plan_issue,
            "execute": capability["allowed"] and not busy,
            "resolve": task["state"] in ("unknown", "partial") or halted,
            "markNotWritten": task["state"] == "unknown" or halted,
        },
        "querying": busy,
    }
