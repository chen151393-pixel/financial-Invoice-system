"""提交和查询后台批次；提交接口不等待上游读取。"""

from datetime import UTC, date, datetime, time
from uuid import uuid4

from backend.core.errors import ApiError

from ..dao import lemon_job_dao as jobs
from ..dao import lemon_plan_dao as plans
from ..dao import sync_run_dao as runs
from ..policy.lemon_batch_policy import ACTIVE, binding_key, retry_allowed, windows
from ..vo.lemon_batch_vo import batch_view, plan_view


class LemonBatchService:
    def __init__(self, accounts):
        self.accounts, self.engine = accounts, accounts.engine

    def scope(self, owner):
        if owner != f"user:{self.accounts.binding.settings.admin_user}":
            raise ApiError(403, "只有本系统管理员可访问同步任务")
        return self.accounts.binding._scope(owner)

    def submit(self, owner, body):
        config = body.model_dump(exclude={"requestId"})
        with self.engine.begin() as connection:
            scope, binding = self.accounts.context(connection, owner, lock=True)
            previous = runs.get(connection, scope, body.requestId)
            if previous:
                self._same(previous, config)
                return batch_view(previous)
            self.enqueue(connection, scope, owner, body.requestId, config, binding)
        return self.read(owner, body.requestId)

    @staticmethod
    def _same(previous, config):
        original = {k: v for k, v in previous["configuration"].items() if k != "bindingKey"}
        if original != config:
            raise ApiError(409, "同一请求编号不能更改同步条件，请查询原任务")

    def enqueue(self, connection, scope, owner, request_id, config, binding, *, plan_id=None, now=None):
        now = now or datetime.now(UTC).replace(tzinfo=None)
        if len(runs.active(connection, scope, ACTIVE)) >= 20:
            raise ApiError(409, "待执行批次已达 20 个，请等待已有任务完成后再提交")
        return runs.create(
            connection,
            {
                "source": "lemon_invoice",
                "account": scope,
                "scope_key": scope,
                "request_id": request_id,
                "plan_id": plan_id,
                "trigger_type": "schedule" if plan_id else "manual",
                "status": "running",
                "phase": "queued",
                "configuration": {**config, "bindingKey": binding_key(binding)},
                "window_start": datetime.combine(date.fromisoformat(config["startDate"]), time()),
                "window_end": datetime.combine(date.fromisoformat(config["endDate"]), time()),
                "started_by": owner,
                "started_at": now,
                "message": "已提交，等待后台执行；关闭页面不影响任务",
            },
        )

    def read(self, owner, request_id, page=1):
        scope = self.scope(owner)
        with self.engine.connect() as connection:
            row = runs.get(connection, scope, request_id)
            if not row:
                raise ApiError(404, "未找到当前账号的后台同步任务")
            result = batch_view(row, jobs.list_jobs(connection, row["id"]))
        total = len(result["accounts"])
        result.update(total=total, page=page, pageSize=20, pages=max(1, (total + 19) // 20))
        result["accounts"] = result["accounts"][(page - 1) * 20 : page * 20]
        return result

    def list(self, owner, page=1, size=20, phase=None):
        scope = self.scope(owner)
        with self.engine.connect() as connection:
            rows, total = runs.list_page(connection, scope, page, size, phase)
            counts = runs.counts(connection, scope)
            plan = plan_view(plans.get(connection, scope))
        return {
            "items": [batch_view(row) for row in rows],
            "total": total,
            "page": page,
            "pageSize": size,
            "pages": max(1, (total + size - 1) // size),
            "counts": counts,
            "plan": {"enabled": plan["enabled"], "nextRunAt": plan["nextRunAt"]},
        }

    def retry(self, owner, request_id, body):
        with self.engine.begin() as connection:
            scope, binding = self.accounts.context(connection, owner, lock=True)
            original = runs.get(connection, scope, request_id)
            if not original:
                raise ApiError(404, "未找到原同步任务")
            config = {k: v for k, v in original["configuration"].items() if k != "bindingKey"}
            config["retryOf"] = request_id
            previous = runs.get(connection, scope, body.requestId)
            if previous:
                self._same(previous, config)
                return batch_view(previous)
            if not retry_allowed(original):
                raise ApiError(409, "当前任务不能重试；执行中或结果待核实的任务须先查询原结果")
            failed = [v for v in jobs.list_jobs(connection, original["id"]) if v["status"] == "failed"]
            run_id = self.enqueue(connection, scope, owner, body.requestId, config, binding)
            jobs.create(
                connection, [job_values(run_id, row, row["start_date"], row["end_date"]) for row in failed]
            )
            runs.change(connection, run_id, phase="running")
        return self.read(owner, body.requestId)


def job_values(run_id, account, start, end):
    return {
        "run_id": run_id,
        "request_id": str(uuid4()),
        "asid": account["asid"],
        "account_name": account.get("name", account.get("account_name")),
        "start_date": start,
        "end_date": end,
        "status": "queued",
    }


def account_jobs(run_id, accounts, config):
    start, end = date.fromisoformat(config["startDate"]), date.fromisoformat(config["endDate"])
    # 队列规模有界；超长历史请按年度提交，避免生成数百万分片。
    periods = list(windows(start, end))
    if len(periods) * len(accounts) > 12000:
        raise ApiError(422, "本次超过 12000 个账套日期分片，请缩小历史范围或减少账套")
    return [job_values(run_id, account, a, b) for account in accounts for a, b in periods]
