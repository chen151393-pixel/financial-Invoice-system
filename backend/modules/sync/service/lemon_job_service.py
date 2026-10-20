"""分片执行与批次汇总。分片即 sync_lemon_runs 中带 run_id 的拉票记录，状态只存这一份。

只有明确超量且未保存的日期范围可以自动拆分；running 却不在本进程执行的分片视为结果待核实，不重新执行。
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import lemon_run_dao as pulls
from ..dao import sync_run_dao as runs
from ..dto.lemon_invoice_dto import PullLemonInvoices
from ..policy.lemon_batch_policy import binding_key, selected_accounts, shard_state, summary
from .lemon_batch_service import account_shards, shard_values

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
            values = account_shards(batch, accounts)
            with self.engine.begin() as connection:
                _, current = self.accounts.context(connection, owner, lock=True)
                self._binding(current, config)
                # 命名锁连接若曾断开，另一个消费者可能已完成发现；以行锁下的事实防止重复建片。
                current_run = runs.get(connection, batch["scope_key"], batch["request_id"], lock=True)
                if current_run["phase"] != "discovering":
                    return
                pulls.create_shards(connection, values)
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
                    message=error.message,
                    finished_at=datetime.now(UTC).replace(tzinfo=None),
                )

    @staticmethod
    def _binding(binding, config):
        if binding_key(binding) != config["bindingKey"]:
            raise ApiError(409, "授权绑定已变化，原任务未继续执行，请重新配置同步范围")

    def execute(self, batch, shard):
        body = PullLemonInvoices(
            requestId=shard["request_id"],
            asid=shard["asid"],
            startDate=shard["start_date"].isoformat(),
            endDate=shard["end_date"].isoformat(),
            businessTypes=batch["configuration"]["businessTypes"],
        )
        claimed = False
        self.batches.executing.add(shard["request_id"])
        try:
            with self.engine.begin() as connection:
                scope, binding = self.accounts.context(connection, batch["started_by"], lock=True)
                if pulls.lock_shard(connection, shard["id"])["status"] != "queued":
                    return
                self._binding(binding, batch["configuration"])
                self.invoices.claim_background(connection, scope, body)
            claimed = True
            self.invoices._execute(batch["started_by"], body, scope, binding, background=True)
        except ApiError as error:
            if error.code == "lemon_range_limit" and shard["start_date"] < shard["end_date"]:
                self._split(batch, shard)
            elif not claimed:
                self._refuse(shard, error.message)
            # 已领取的分片以本行持久提交事实为准，_execute 已写入 failed。
        except SQLAlchemyError:
            logger.error("lemon_job_database_uncertain shard=%s", shard["id"])
        except Exception as error:  # noqa: BLE001 -- 后台隔离边界，保留未知结果且仅记录异常类型
            # 线程隔离边界：不回显异常正文或自动重试，保留原子请求供核实。
            logger.error("lemon_job_unexpected shard=%s type=%s", shard["id"], type(error).__name__)
        finally:
            self.batches.executing.discard(shard["request_id"])
        self.reconcile(batch)

    def _refuse(self, shard, message):
        """领取前即被拒绝（绑定变化、同账套互斥）的分片没有执行，记为失败可重试。"""
        with self.engine.begin() as connection:
            pulls.lock_shard(connection, shard["id"])
            pulls.mark(connection, shard["id"], "failed", expected="queued", error=message[:500])

    def _split(self, batch, shard):
        middle = shard["start_date"] + (shard["end_date"] - shard["start_date"]) // 2
        with self.engine.begin() as connection:
            current = pulls.lock_shard(connection, shard["id"])
            if current["status"] != "failed":
                return
            # 原失败原因保留在已拆分行上，两个子分片重新排队。
            pulls.mark(connection, shard["id"], "split", expected="failed", error=current["error"])
            pulls.create_shards(
                connection,
                [
                    shard_values(batch, shard, shard["start_date"], middle),
                    shard_values(batch, shard, middle + timedelta(days=1), shard["end_date"]),
                ],
            )

    def reconcile(self, batch):
        """只汇总，不改分片状态：批次阶段与统计由分片行实时计算后写入 sync_runs。"""
        now = datetime.now(UTC).replace(tzinfo=None)
        executing = frozenset(self.batches.executing)
        with self.engine.begin() as connection:
            rows = pulls.batch_shards(connection, batch["id"])
            phase, counts = summary(rows, executing)
            failed = sum(shard_state(v, executing) == "failed" for v in rows)
            runs.change(
                connection,
                batch["id"],
                phase=phase,
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
