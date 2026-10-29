"""同一审核事务内入队；不访问外部系统。"""

from datetime import datetime, timezone
from uuid import uuid4

from backend.modules.matching.public import read_writeback_snapshot

from ..dao import audit_dao, task_dao
from ..policy.state_policy import WRITTEN_STATES


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def stale(connection, task, reason):
    if task["state"] == "stale":
        return
    if task["state"] in WRITTEN_STATES:
        note = f"审核内容在写入 NS 后已变化（{reason}），须人工核对 NS 登记"[:500]
        if task["reason"] != note:
            stamp = now()
            task_dao.change(connection, task["id"], {"reason": note}, stamp)
            audit_dao.add(connection, task["id"], "changed_after_write", "system", {"reason": reason}, stamp)
        return
    stamp = now()
    task_dao.change(
        connection,
        task["id"],
        {
            "state": "stale",
            "reason": reason,
            "revision": task["revision"] + 1,
            "lease_token": None,
            "lease_until": None,
        },
        stamp,
    )
    audit_dao.add(connection, task["id"], "invalidated", "system", {"reason": reason}, stamp)


def still_current(connection, task):
    result = read_writeback_snapshot(connection, task["invoice_id"])
    if task["state"] == "stale":
        return False
    if not result["ready"] or result["fingerprint"] != task["fingerprint"]:
        stale(connection, task, result["reason"] if not result["ready"] else "审核内容已变化，请重新核对")
        return False
    return True


def enqueue(connection, invoice_id, actor, *, historical=False):
    result = read_writeback_snapshot(connection, invoice_id)
    previous = task_dao.current(connection, invoice_id)
    if previous and (not result["ready"] or previous["fingerprint"] != result["fingerprint"]):
        stale(connection, previous, result["reason"] if not result["ready"] else "审核内容已变化")
    if not result["ready"]:
        return result
    existing = task_dao.by_snapshot(connection, invoice_id, result["fingerprint"])
    if existing:
        return {**result, "taskId": str(existing["id"])}
    snapshot = result["snapshot"]
    source = next(iter(snapshot["sources"].values()))
    stamp = now()
    task_id = task_dao.add(
        connection,
        {
            "task_no": "NSWB-" + uuid4().hex,
            "invoice_id": invoice_id,
            "fingerprint": result["fingerprint"],
            "snapshot": snapshot,
            "ns_account": source["ns_account"],
            "vendor_id": source["vendor_id"],
            "vendor_name": source["vendor_name"],
            "invoice_no": snapshot["invoice"]["invoice_no"],
            "amount": snapshot["invoice"]["amount_including_tax"],
            "state": "queued",
            "reason": "等待查询候选账单",
            "historical": historical,
            "revision": 1,
        },
        stamp,
    )
    audit_dao.add(connection, task_id, "queued", actor, {"historical": historical}, stamp)
    return {**result, "taskId": str(task_id)}


def on_matching_changed(connection, event, *, enabled=True):
    for invoice_id in sorted(set(event.invoice_ids)):
        if enabled:
            enqueue(connection, invoice_id, event.actor)
        else:
            previous = task_dao.current(connection, invoice_id)
            if previous:
                still_current(connection, previous)
