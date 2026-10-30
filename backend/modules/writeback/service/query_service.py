"""先领取只读租约，事务外查询，再核验版本保存；租约不是 NS 写锁。"""

from datetime import timedelta
from uuid import uuid4

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import audit_dao, task_dao
from ..policy.plan_policy import automatic_targets, candidates
from ..policy.state_policy import WRITTEN_STATES
from .queue_service import now, still_current
from .task_service import save_plan


class QueryService:
    def __init__(self, tasks, gateway):
        self.tasks, self.gateway = tasks, gateway

    def refresh(self, task_id, revision, actor):
        lease, claimed = None, None
        with transaction(self.tasks.engine) as connection:
            task = self.tasks.require_task(connection, task_id)
            if task["state"] in WRITTEN_STATES:
                raise ApiError(409, "任务已发出或完成 NS 写入，不能重新查询")
            if still_current(connection, task):
                stamp = now()
                if revision != task["revision"] or (task["lease_until"] and task["lease_until"] > stamp):
                    raise ApiError(409, "任务已变化或正在查询，请稍后刷新")
                lease = str(uuid4())
                task_dao.change(
                    connection,
                    task_id,
                    {
                        "lease_token": lease,
                        "lease_until": stamp + timedelta(minutes=5),
                        "revision": revision + 1,
                        "state": "queued",
                        "reason": "正在查询候选账单",
                        "current_plan_id": None,
                        "candidates": None,
                    },
                    stamp,
                )
                claimed = task
        if not lease:
            raise ApiError(409, "审核快照已失效")
        result, failure = None, None
        try:
            result = self.gateway.query_ids(
                claimed["vendor_id"],
                sorted({s["parent_id"] for s in claimed["snapshot"]["sources"].values()}),
                claimed["invoice_no"],
            )
            result = result.model_dump(mode="json")
        except ApiError as error:
            failure = error.message
        # 不吞掉程序错误；进程退出或异常后只读租约到期即可重查。
        with transaction(self.tasks.engine) as connection:
            task = self.tasks.require_task(connection, task_id)
            # 租约已被取代或审核已失效：丢弃本次结果，按当前状态返回。
            if task["lease_token"] == lease and still_current(connection, task):
                stamp = now()
                state, reason, targets = "blocked", failure, None
                if result:
                    try:
                        registrations = (result.get("registrationCheck") or {}).get("records", [])
                        if registrations:
                            state = "conflict"
                            reason = "NS 已有同号发票登记，已拦截重复回写；记录 ID：" + "、".join(
                                row["id"] for row in registrations[:10]
                            )
                        elif any(o["status"] == "NO_BILLS" for o in result["purchaseOrders"]):
                            candidates(task, result)
                            state, reason = "waiting_bill", "部分母采购尚无可见账单，稍后重查"
                        else:
                            candidates(task, result)
                            targets = automatic_targets(task, result)
                            state, reason = (
                                "needs_confirmation",
                                "请核实实际采购子公司、账单归属及各笔分配金额",
                            )
                    except ApiError as error:
                        reason = error.message
                task_dao.change(
                    connection,
                    task_id,
                    {
                        "state": state,
                        "reason": reason,
                        "candidates": result,
                        "queried_at": stamp,
                        "revision": task["revision"] + 1,
                        "lease_token": None,
                        "lease_until": None,
                        "next_query_at": stamp + timedelta(minutes=10),
                    },
                    stamp,
                )
                audit_dao.add(
                    connection,
                    task_id,
                    "queried" if result else "query_failed",
                    actor,
                    {"reason": reason, "queryId": result.get("queryId") if result else None},
                    stamp,
                )
                if targets:
                    current = task_dao.get(connection, task_id)
                    save_plan(
                        connection,
                        current,
                        targets,
                        str(uuid4()),
                        "automatic",
                        "system",
                        "精确子采购关联及真实子公司映射唯一，所有金额校验通过",
                    )
        return self.tasks.get(task_id)
