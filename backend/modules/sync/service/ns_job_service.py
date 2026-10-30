"""NS 计划批次执行：每轮推进最早的活动批次一页，分页执行复用 NsRunService 与 source 保存流程。

每页只读 NS，保存由 source 按 NS 身份更新已有单据、补齐字段、新增缺失单据；同一账户的保存仍由
source 账户锁互斥，手动同步占用锁时本页记为未写入失败，间隔后按原游标重新排队。
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from backend.core.errors import ApiError

from ..dao import ns_run_dao as pages
from ..dao import sync_run_dao as runs
from ..dto.ns_run_dto import NsRunRequest
from ..policy.ns_plan_policy import ACTIVE, PAGE_LIMIT, PAUSED_ADMIN, PAUSED_UNKNOWN, next_step, summary

logger = logging.getLogger(__name__)


class NsJobService:
    def __init__(self, batches, plans):
        self.batches, self.plans, self.engine = batches, plans, batches.engine
        self.ns_runs, self.require_admin = batches.ns_runs, batches.require_admin

    def step(self, now=None):
        """推进一步；返回 True 表示本轮有进展（执行了一页或结束了批次）。"""
        now = now or datetime.now(UTC).replace(tzinfo=None)
        scope = self.batches.scope()
        with self.engine.connect() as connection:
            active = runs.active(connection, scope, ACTIVE)
            if not active:
                return False
            batch = active[0]
            rows = pages.batch_pages(connection, batch["id"])
        step = next_step(rows, self.ns_runs.executing(scope), now)
        if step["action"] == "wait":
            return False
        if step["action"] == "finish":
            self._finish(batch, rows, step["phase"], step["message"], now)
            return True
        self._execute(batch, rows, step, now)
        return True

    def _execute(self, batch, rows, step, now):
        config, owner = batch["configuration"], batch["started_by"]
        try:
            self.require_admin(owner)
        except ApiError:
            self.plans.pause(batch["scope_key"], PAUSED_ADMIN, now)
            self._finish(batch, rows, "partial" if rows else "failed", PAUSED_ADMIN, now)
            return
        try:
            # 配置类问题（存储未就绪、记录类型未授权）不建分页记录，直接结束本批并说明原因。
            self.ns_runs.pulls.ensure_storage(config["kind"])
            body = NsRunRequest(
                requestId=str(uuid4()),
                kind=config["kind"],
                offset=step["offset"],
                limit=PAGE_LIMIT,
                startDate=config["startDate"],
                endDate=config["endDate"],
                requireDateRange=True,
                cursor=step["cursor"],
            )
        except ApiError as error:
            self._finish(batch, rows, "partial" if rows else "failed", error.message[:500], now)
            return
        except ValidationError:
            self._finish(batch, rows, "partial" if rows else "failed", "分页游标无效，已停止本批", now)
            return
        with self.engine.begin() as connection:
            runs.change(
                connection,
                batch["id"],
                phase="running",
                message=f"正在执行第 {len(rows) + 1} 页，关闭页面不影响任务",
                updated_at=now,
            )
        self.ns_runs.execute_now(owner, batch["scope_key"], body, batch["id"])
        with self.engine.begin() as connection:
            self._counts(connection, batch, pages.batch_pages(connection, batch["id"]))

    def _counts(self, connection, batch, rows, **values):
        counts = summary(rows)
        runs.change(
            connection,
            batch["id"],
            fetched_count=counts["fetched"],
            created_count=counts["created"],
            updated_count=counts["updated"],
            failed_count=counts["failed"],
            updated_at=datetime.now(UTC).replace(tzinfo=None),
            **values,
        )

    def _finish(self, batch, rows, phase, message, now):
        with self.engine.begin() as connection:
            current = runs.get(connection, batch["scope_key"], batch["request_id"], lock=True)
            if current["phase"] not in ACTIVE:
                return
            self._counts(
                connection,
                batch,
                rows,
                phase=phase,
                message=message,
                # 待核实批次没有确定的结束时间，与柠檬云批次口径一致。
                finished_at=None if phase == "unknown" else now,
            )
        if phase == "unknown" and batch["ns_plan_id"]:
            # 结果待核实不能被下一次计划绕过：自动暂停，由管理员核对后重新启用。
            self.plans.pause(batch["scope_key"], PAUSED_UNKNOWN, now)
            logger.warning("ns_schedule_paused reason=unknown_page batch=%s", batch["id"])
