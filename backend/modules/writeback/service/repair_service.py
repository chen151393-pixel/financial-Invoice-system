"""账单补写（2026-11-10）：NS 已建发票记录、账单累计未全部更新（partial）时，只补写账单，不新建发票记录。

- 只处理 partial 且已记录发票记录 ID 的任务；写入开关与供应商白名单同正常写入。
- 沿用原写入请求的冻结正文与请求编号，附 action=repair 和发票记录 ID；NS 端核对发票记录与明细，
  逐张账单判定已补齐、待补写或累计已变化，任一不符整单不改。
- 账单锁在 partial 时一直保留；补写全部完成才释放。与正常写入一样短事务登记、事务外调用、短事务记录结果；
  结果不明转 unknown，须人工在 NS 核实，不自动重试。
"""

import logging

from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.integrations.netsuite.client import WriteOutcomeUnknown

from ..dao import audit_dao, lock_dao, request_dao, task_dao
from ..policy.repair_policy import repair_allowed
from ..policy.result_policy import interpret_repair, unknown
from .queue_service import now
from .task_service import require_user

logger = logging.getLogger(__name__)


class RepairService:
    def __init__(self, tasks, gateway):
        self.tasks, self.gateway = tasks, gateway

    def repair(self, task_id, revision, actor):
        require_user(actor)
        with transaction(self.tasks.engine) as connection:
            task = self.tasks.require_task(connection, task_id)
            if revision != task["revision"]:
                raise ApiError(409, "任务已变化，请刷新后再补写")
            request = (
                request_dao.by_plan(connection, task["current_plan_id"]) if task["current_plan_id"] else None
            )
            allowed, reason = repair_allowed(task, request, self.tasks.gate)
            if not allowed:
                raise ApiError(409, reason)
            bill_ids = [line["billId"] for line in request["payload"]["bills"]]
            # partial 时账单锁由本请求持有；被其他回写占用说明锁已异常释放，不能补写
            held = lock_dao.holders(connection, self.tasks.account, bill_ids)
            foreign = sorted(bill_id for bill_id, holder in held.items() if holder != request["id"])
            if foreign:
                raise ApiError(409, f"账单 {'、'.join(foreign)} 正被其他回写占用，请先处理该回写结果")
            missing = [bill_id for bill_id in bill_ids if bill_id not in held]
            stamp = now()
            if missing:
                lock_dao.acquire(connection, self.tasks.account, missing, request["id"], stamp)
            request_dao.change(connection, request["id"], {"state": "executing", "sent_at": stamp}, stamp)
            task_dao.change(
                connection,
                task_id,
                {"state": "executing", "reason": "正在补写 NS 账单", "revision": task["revision"] + 1},
                stamp,
            )
            audit_dao.add(
                connection,
                task_id,
                "repair_started",
                actor,
                {"requestId": request["request_id"], "nsRecordId": request["ns_record_id"]},
                stamp,
            )
        payload = {**request["payload"], "action": "repair", "invoiceRecordId": request["ns_record_id"]}
        try:
            response = self.gateway.vendor_bill_writeback(payload)
            outcome = interpret_repair(request, response, self.tasks.account)
            outcome["response"] = response
        except WriteOutcomeUnknown:
            outcome = unknown("NS 补写请求已发出但未得到结果，请在 NS 核实账单后标记")
        except ApiError as error:
            outcome = {"state": "not_written", "reason": error.message, "release": False}
        except Exception:
            logger.exception("回写任务 %s 补写账单异常", task_id)
            outcome = unknown("补写过程出现程序异常，结果不明，请在 NS 核实后标记")
        self._record(task_id, request, outcome, actor)
        return self.tasks.get(task_id)

    def _record(self, task_id, request, outcome, actor):
        with transaction(self.tasks.engine) as connection:
            task = task_dao.get(connection, task_id)
            stamp = now()
            reason = outcome["reason"][:500]
            state = outcome["state"]
            # 未改动账单时回到 partial，可处理原因后再次补写；结果保留原写入返回与本次补写返回
            request_state = "partial" if state == "not_written" else state
            task_state = "partial" if state == "not_written" else state
            result = {"previous": request["result"], "repair": outcome.get("response")}
            values = {"state": request_state, "result": result}
            if state == "applied":
                values["finished_at"] = stamp
            request_dao.change(connection, request["id"], values, stamp)
            task_dao.change(
                connection,
                task_id,
                {"state": task_state, "reason": reason, "revision": task["revision"] + 1},
                stamp,
            )
            if outcome["release"]:
                lock_dao.release(connection, request["id"])
            audit_dao.add(
                connection,
                task_id,
                "repair_finished",
                actor,
                {"state": state, "reason": reason, "nsRecordId": request["ns_record_id"]},
                stamp,
            )
