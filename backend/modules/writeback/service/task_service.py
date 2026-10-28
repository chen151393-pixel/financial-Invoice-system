"""准备任务查询及人工目标确认；没有 NS 写入入口。"""

import hashlib

from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.modules.matching.public import read_writeback_snapshot, writeback_invoice_ids

from ..dao import audit_dao, plan_dao, task_dao
from ..policy.plan_policy import validate_plan
from ..vo.task_vo import detail, summary
from .queue_service import enqueue, now, still_current


def require_user(actor):
    if actor.startswith("service:"):
        raise ApiError(403, "服务身份只读，不能确认或重新检查回写任务")


class TaskService:
    def __init__(self, engine, account, *, queue_enabled=True):
        self.engine, self.account = engine, account
        self.queue_enabled = queue_enabled

    def scoped(self, connection, task_id):
        task = task_dao.get(connection, task_id)
        if not task or task["ns_account"].lower().replace("-", "_") != self.account.lower().replace("-", "_"):
            raise ApiError(404, "任务不存在或不属于当前 NS 账套")
        return task

    def list(self, criteria):
        with self.engine.connect() as connection:
            rows, total = task_dao.page(connection, self.account, criteria)
        return {
            "items": [summary(row) for row in rows],
            "total": total,
            "page": criteria.page,
            "pageSize": criteria.pageSize,
            "pages": max(1, (total + criteria.pageSize - 1) // criteria.pageSize),
        }

    def get(self, task_id):
        with transaction(self.engine) as connection:
            task = self.scoped(connection, task_id)
            still_current(connection, task)
            task = self.scoped(connection, task_id)
            plan = plan_dao.get(connection, task["current_plan_id"]) if task["current_plan_id"] else None
            busy = bool(task["lease_until"] and task["lease_until"] > now())
            return detail(task, plan, audit_dao.recent(connection, task_id), busy)

    def invoice(self, invoice_id):
        with self.engine.connect() as connection:
            result = read_writeback_snapshot(connection, invoice_id)
            task = task_dao.current(connection, invoice_id)
        visible = task and task["ns_account"] == self.account
        return {
            "ready": result["ready"],
            "reason": result["reason"],
            "task": summary(task) if visible else None,
        }

    def recheck(self, invoice_id, actor):
        require_user(actor)
        if not self.queue_enabled:
            raise ApiError(409, "自动入队已关闭，请由管理员启用后重新检查")
        with transaction(self.engine) as connection:
            enqueue(connection, invoice_id, actor, historical=True)
        return self.invoice(invoice_id)

    def scan(self, after_id):
        if not self.queue_enabled:
            return 0
        with transaction(self.engine) as connection:
            ids = writeback_invoice_ids(connection, after_id)
            for invoice_id in ids:
                enqueue(connection, invoice_id, "system", historical=True)
        return ids[-1] if ids else 0

    def confirm(self, task_id, body, actor):
        require_user(actor)
        digest = hashlib.sha256((actor + body.model_dump_json()).encode()).hexdigest()
        invalid = False
        with transaction(self.engine) as connection:
            task = self.scoped(connection, task_id)
            if not still_current(connection, task):
                invalid = True
            else:
                previous = plan_dao.by_request(connection, task_id, str(body.requestId))
                if previous and previous["request_hash"] != digest:
                    raise ApiError(409, "请求编号已用于其他确认正文或身份")
                if not previous:
                    if (
                        body.revision != task["revision"]
                        or task["state"] != "needs_confirmation"
                        or (task["lease_until"] and task["lease_until"] > now())
                    ):
                        raise ApiError(409, "任务或候选版本已变化，请刷新后确认")
                    if len(body.evidence.strip()) < 5:
                        raise ApiError(422, "请填写实际公司与账单归属的核实依据")
                    targets = validate_plan(
                        task, task["candidates"], [t.model_dump() for t in body.allocations]
                    )
                    save_plan(
                        connection, task, targets, str(body.requestId), digest, actor, body.evidence.strip()
                    )
        if invalid:
            raise ApiError(409, "审核快照已失效，请重新核实发票分配")
        return self.get(task_id)


def save_plan(connection, task, targets, request_id, digest, actor, evidence):
    stamp = now()
    body = {
        "allocations": targets,
        "evidence": evidence,
        "confirmedBy": actor,
        "confirmedAt": stamp.isoformat(),
        "candidates": task["candidates"],
        "approvalFingerprint": task["fingerprint"],
    }
    plan_id = plan_dao.add(
        connection,
        {
            "task_id": task["id"],
            "revision": task["revision"],
            "request_id": request_id,
            "request_hash": digest,
            "body": body,
            "confirmed_by": actor,
        },
        stamp,
    )
    task_dao.change(
        connection,
        task["id"],
        {
            "current_plan_id": plan_id,
            "state": "ready",
            "reason": "方案已冻结；NS 写入尚未接入，查询额度未预留",
            "revision": task["revision"] + 1,
        },
        stamp,
    )
    audit_dao.add(
        connection, task["id"], "plan_confirmed", actor, {"planId": str(plan_id), "evidence": evidence}, stamp
    )
