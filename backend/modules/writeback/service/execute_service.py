"""NS 写入：短事务加锁并登记 executing，事务外调用写入 RESTlet，再短事务记录结果。

结果不明或部分完成时保留账单锁，只能人工在 NS 核实后标记结论，不提供直接重发。
"""

import logging

from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.integrations.netsuite.client import WriteOutcomeUnknown

from ..dao import audit_dao, lock_dao, plan_dao, request_dao, task_dao
from ..policy.order_policy import require_whole_orders
from ..policy.registration_policy import require_clear_registration
from ..policy.result_policy import interpret, unknown
from ..policy.state_policy import stuck
from .queue_service import now, still_current
from .task_service import require_user

logger = logging.getLogger(__name__)

TASK_STATES = {
    "applied": "applied",
    "conflict": "conflict",
    "rejected": "blocked",
    "partial": "partial",
    "unknown": "unknown",
}


class ExecuteService:
    def __init__(self, tasks, gateway):
        self.tasks, self.gateway = tasks, gateway

    def confirm_preview(self, task_id, body, actor):
        require_user(actor)
        invalid = False
        with transaction(self.tasks.engine) as connection:
            task = self.tasks.require_task(connection, task_id)
            if not still_current(connection, task):
                invalid = True
            else:
                if body.revision != task["revision"] or task["state"] != "needs_preview":
                    raise ApiError(409, "任务已变化，请刷新后确认预览")
                request = request_dao.by_plan(connection, task["current_plan_id"])
                stamp = now()
                request_dao.change(
                    connection, request["id"], {"confirmed_by": actor, "confirmed_at": stamp}, stamp
                )
                task_dao.change(
                    connection,
                    task_id,
                    {
                        "state": "ready",
                        "reason": "回写预览已确认，等待写入 NS",
                        "revision": task["revision"] + 1,
                    },
                    stamp,
                )
                audit_dao.add(
                    connection,
                    task_id,
                    "preview_confirmed",
                    actor,
                    {"requestId": request["request_id"]},
                    stamp,
                )
        if invalid:
            raise ApiError(409, "审核快照已失效，请重新核实发票分配")
        return self.tasks.get(task_id)

    def execute(self, task_id, revision, actor):
        require_user(actor)
        invalid = False
        with transaction(self.tasks.engine) as connection:
            task = self.tasks.require_task(connection, task_id)
            if revision != task["revision"]:
                raise ApiError(409, "任务已变化，请刷新后再写入")
            if task["state"] != "ready":
                raise ApiError(409, "任务不是待写入状态")
            if not still_current(connection, task):
                invalid = True
            else:
                request = self._claim(connection, task, actor)
        if invalid:
            raise ApiError(409, "审核快照已失效，请重新核实发票分配")
        # 写入开始后不再因审核变化或程序错误丢掉结果：一律落库为可核实的状态。
        try:
            response = self.gateway.vendor_bill_writeback(request["payload"])
            outcome = interpret(request, response, self.tasks.account)
            outcome["response"] = response
        except WriteOutcomeUnknown:
            outcome = unknown("NS 写入请求已发出但未得到结果，请在 NS 核实后标记")
        except ApiError as error:
            outcome = {"state": "not_sent", "reason": error.message, "release": True, "record": None}
        except Exception:
            logger.exception("回写任务 %s 写入调用异常", task_id)
            outcome = unknown("写入过程出现程序异常，结果不明，请在 NS 核实后标记")
        self._record(task_id, request, outcome, actor)
        return self.tasks.get(task_id)

    def _claim(self, connection, task, actor):
        require_clear_registration(task, task["candidates"])
        allowed, reason = self.tasks.gate.check(task)
        if not allowed:
            raise ApiError(409, reason)
        plan = plan_dao.get(connection, task["current_plan_id"])
        if not plan:
            raise ApiError(409, "冻结方案不存在，请重新查询账单")
        # 历史正文保持不可变；旧的拆单方案须重查确认后再执行。
        require_whole_orders(task, plan["body"]["allocations"])
        request = request_dao.by_plan(connection, task["current_plan_id"])
        if (
            not request
            or request["state"] != "pending"
            or (request["needs_confirmation"] and not request["confirmed_by"])
        ):
            raise ApiError(409, "写入请求未就绪，请先确认回写预览")
        bill_ids = [line["billId"] for line in request["payload"]["bills"]]
        held = lock_dao.holders(connection, self.tasks.account, bill_ids)
        if held:
            raise ApiError(409, f"账单 {'、'.join(sorted(held))} 正被其他回写占用，请先处理该回写结果")
        stamp = now()
        lock_dao.acquire(connection, self.tasks.account, bill_ids, request["id"], stamp)
        request_dao.change(connection, request["id"], {"state": "executing", "sent_at": stamp}, stamp)
        task_dao.change(
            connection,
            task["id"],
            {"state": "executing", "reason": "正在写入 NS", "revision": task["revision"] + 1},
            stamp,
        )
        audit_dao.add(
            connection, task["id"], "write_started", actor, {"requestId": request["request_id"]}, stamp
        )
        return request

    def _record(self, task_id, request, outcome, actor):
        with transaction(self.tasks.engine) as connection:
            task = task_dao.get(connection, task_id)
            stamp = now()
            reason = outcome["reason"][:500]
            if outcome["state"] == "not_sent":
                request_values = {"state": "pending"}
                task_values = {"state": "ready", "reason": f"写入请求未发出：{reason}"[:500]}
            else:
                request_values = {"state": outcome["state"], "result": outcome.get("response")}
                if outcome["state"] not in ("unknown", "partial"):
                    request_values["finished_at"] = stamp
                if outcome["record"]:
                    request_values["ns_record_id"] = outcome["record"]
                task_values = {"state": TASK_STATES[outcome["state"]], "reason": reason}
            request_dao.change(connection, request["id"], request_values, stamp)
            task_dao.change(connection, task_id, {**task_values, "revision": task["revision"] + 1}, stamp)
            if outcome["release"]:
                lock_dao.release(connection, request["id"])
            audit_dao.add(
                connection,
                task_id,
                "write_finished",
                actor,
                {"state": outcome["state"], "reason": reason, "nsRecordId": outcome["record"]},
                stamp,
            )

    def resolve(self, task_id, body, actor):
        require_user(actor)
        with transaction(self.tasks.engine) as connection:
            task = self.tasks.require_task(connection, task_id)
            request = (
                request_dao.by_plan(connection, task["current_plan_id"]) if task["current_plan_id"] else None
            )
            if body.revision != task["revision"] or not request:
                raise ApiError(409, "任务已变化，请刷新后核实")
            if task["state"] not in ("unknown", "partial") and not stuck(task, request, now()):
                raise ApiError(409, "只有结果不明或部分完成的任务需要人工核实")
            if body.outcome == "not_written" and task["state"] == "partial":
                raise ApiError(409, "NS 已建发票记录，不能标记为未写入")
            stamp = now()
            resolution = {
                "outcome": body.outcome,
                "evidence": body.evidence.strip(),
                "nsRecordId": body.nsRecordId,
                "resolvedBy": actor,
                "resolvedAt": stamp.isoformat(),
                "previous": request["result"],
            }
            if body.outcome == "applied":
                request_values = {
                    "state": "applied",
                    "result": resolution,
                    "ns_record_id": body.nsRecordId or request["ns_record_id"],
                    "finished_at": stamp,
                }
                task_values = {"state": "applied", "reason": "已人工核实 NS 已登记"}
            else:
                # 人工确认 NS 没有任何写入后才允许再次写入；NS 端仍按同号发票和写前累计拦截重复。
                request_values = {"state": "pending", "result": resolution}
                task_values = {"state": "ready", "reason": "已人工核实 NS 未写入，可重新写入"}
            request_dao.change(connection, request["id"], request_values, stamp)
            task_dao.change(connection, task_id, {**task_values, "revision": task["revision"] + 1}, stamp)
            lock_dao.release(connection, request["id"])
            audit_dao.add(
                connection,
                task_id,
                "write_resolved",
                actor,
                {"outcome": body.outcome, "evidence": resolution["evidence"], "nsRecordId": body.nsRecordId},
                stamp,
            )
        return self.tasks.get(task_id)

    def run_ready(self):
        """后台自动写入：只处理已就绪且通过写入开关和白名单的任务，每轮最多 4 个。"""
        with self.tasks.engine.connect() as connection:
            rows = task_dao.ready_to_write(connection)
        for row in rows:
            if not self.tasks.gate.check(row)[0]:
                continue
            try:
                self.execute(row["id"], row["revision"], "system")
            except ApiError as error:
                logger.info("回写任务 %s 本轮未写入：%s", row["id"], error.message)
