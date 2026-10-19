"""分片执行与提交核实。只有明确超量且未保存的日期范围可以自动拆分。"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import lemon_job_dao as jobs
from ..dao import lemon_run_dao as invoices
from ..dao import sync_run_dao as runs
from ..dto.lemon_invoice_dto import PullLemonInvoices
from ..policy.lemon_batch_policy import binding_key, selected_accounts, summary
from .lemon_batch_service import account_jobs, job_values

logger = logging.getLogger(__name__)


class LemonJobService:
    def __init__(self, batches, invoice_service):
        self.batches, self.invoices = batches, invoice_service
        self.accounts, self.engine = batches.accounts, batches.engine

    def discover(self, batch):
        owner, config = batch["started_by"], batch["configuration"]
        try:
            with self.engine.begin() as connection:
                _, binding = self.accounts.context(connection, owner, lock=True)
                current_run = runs.get(connection, batch["scope_key"], batch["request_id"], lock=True)
                if current_run["phase"] not in ("queued", "discovering"):
                    return
                self._binding(binding, config)
                runs.change(connection, batch["id"], phase="discovering")
            token = self.accounts.client.user_token(binding["mobile"])
            accounts = selected_accounts(self.accounts.authorized_accounts(token), config)
            values = account_jobs(batch["id"], accounts, config)
            with self.engine.begin() as connection:
                _, current = self.accounts.context(connection, owner, lock=True)
                self._binding(current, config)
                # 命名锁连接若曾断开，另一个消费者可能已完成发现；以行锁下的事实防止重复建片。
                current_run = runs.get(connection, batch["scope_key"], batch["request_id"], lock=True)
                if current_run["phase"] != "discovering":
                    return
                jobs.create(connection, values)
                runs.change(
                    connection,
                    batch["id"],
                    phase="running",
                    message=f"已发现并纳入 {len(accounts)} 个账套，按日期分批执行",
                )
        except ApiError as error:
            with self.engine.begin() as connection:
                current_run = runs.get(connection, batch["scope_key"], batch["request_id"], lock=True)
                if current_run["phase"] not in ("queued", "discovering"):
                    return
                runs.change(
                    connection,
                    batch["id"],
                    phase="failed",
                    status="failed",
                    message=error.message,
                    finished_at=datetime.now(UTC).replace(tzinfo=None),
                )

    @staticmethod
    def _binding(binding, config):
        if binding_key(binding) != config["bindingKey"]:
            raise ApiError(409, "授权绑定已变化，原任务未继续执行，请重新配置同步范围")

    def execute(self, batch, job):
        body = PullLemonInvoices(
            requestId=job["request_id"],
            asid=job["asid"],
            startDate=job["start_date"].isoformat(),
            endDate=job["end_date"].isoformat(),
            businessTypes=batch["configuration"]["businessTypes"],
        )
        prepared = False
        try:
            with self.engine.begin() as connection:
                scope, binding = self.accounts.context(connection, batch["started_by"], lock=True)
                current_job = jobs.get(connection, job["id"])
                if current_job["status"] != "queued":
                    return
                self._binding(binding, batch["configuration"])
                self.invoices.prepare_background(connection, batch["started_by"], body, job["account_name"])
                jobs.change(connection, job["id"], "running", datetime.now(UTC).replace(tzinfo=None))
            prepared = True
            self.invoices._execute(batch["started_by"], body, scope, binding, background=True)
        except ApiError as error:
            if error.code == "lemon_range_limit" and job["start_date"] < job["end_date"]:
                self._split(batch, job)
            elif not prepared:
                self._finish(job, "failed", error.message)
            # 已领取的请求以 sync_lemon_runs 的持久提交事实为准。
        except SQLAlchemyError:
            logger.error("lemon_job_database_uncertain job=%s", job["id"])
        except Exception as error:  # noqa: BLE001 -- 后台隔离边界，保留未知结果且仅记录异常类型
            # 线程隔离边界：不回显异常正文或自动重试，保留原子请求供核实。
            logger.error("lemon_job_unexpected job=%s type=%s", job["id"], type(error).__name__)
        self.reconcile(batch)

    def _finish(self, job, status, error=None):
        with self.engine.begin() as connection:
            if jobs.get(connection, job["id"])["status"] != "queued":
                return
            jobs.change(connection, job["id"], status, datetime.now(UTC).replace(tzinfo=None), error)

    def _split(self, batch, job):
        middle = job["start_date"] + (job["end_date"] - job["start_date"]) // 2
        with self.engine.begin() as connection:
            if jobs.get(connection, job["id"])["status"] == "split":
                return
            saved = invoices.get(connection, batch["scope_key"], job["request_id"])
            if not saved or saved["status"] != "failed":
                return
            jobs.change(connection, job["id"], "split", datetime.now(UTC).replace(tzinfo=None))
            jobs.create(
                connection,
                [
                    job_values(batch["id"], job, job["start_date"], middle),
                    job_values(batch["id"], job, middle + timedelta(days=1), job["end_date"]),
                ],
            )

    def reconcile(self, batch):
        now = datetime.now(UTC).replace(tzinfo=None)
        with self.engine.begin() as connection:
            rows = jobs.list_jobs(connection, batch["id"])
            for job in rows:
                if job["status"] not in ("running", "unknown"):
                    continue
                saved = invoices.get(connection, batch["scope_key"], job["request_id"])
                state = saved["status"] if saved and saved["status"] in ("completed", "failed") else "unknown"
                error = (
                    saved["error"]
                    if saved and state == "failed"
                    else ("执行曾中断，提交结果待核实；禁止直接重试" if state == "unknown" else None)
                )
                jobs.change(connection, job["id"], state, now, error)
            rows = jobs.list_jobs(connection, batch["id"])
            phase, counts = summary(rows)
            failed = sum(v["status"] == "failed" for v in rows)
            runs.change(
                connection,
                batch["id"],
                phase=phase,
                status={"completed": "succeeded", "partial": "partial", "failed": "failed"}.get(
                    phase, "running"
                ),
                fetched_count=counts["fetched"],
                created_count=counts["created"],
                updated_count=counts["updated"],
                failed_count=failed,
                message={
                    "completed": "全部账套日期分片已完成；无新增属于正常结果，明细完整性请查看统计",
                    "partial": "部分日期分片失败，其余已提交；可仅重试明确失败的分片",
                    "failed": "本批次未完成，请展开账套查看失败原因",
                    "unknown": "存在提交结果待核实的分片，禁止直接重试",
                }.get(phase, "正在按账套和日期分片执行，关闭页面不影响任务"),
                updated_at=now,
                finished_at=None if phase in ("running", "unknown") else now,
            )
        return rows
