"""柠檬云后台消费者与每日调度；常驻循环与数据库命名锁见 ScheduledWorker。"""

import logging

from backend.core.errors import ApiError

from ..dao import sync_run_dao as runs
from ..policy.lemon_batch_policy import ACTIVE
from .scheduled_worker import ScheduledWorker

logger = logging.getLogger(__name__)


class LemonWorker(ScheduledWorker):
    lock_prefix, thread_name, log_name = "lemon-worker", "lemon-sync", "lemon_worker"

    def __init__(self, plans, jobs):
        super().__init__(jobs.engine)
        self.plans, self.jobs = plans, jobs
        self.owner = f"user:{jobs.accounts.binding.settings.admin_user}"
        self.scope = jobs.batches.scope(self.owner)

    def _consume(self):
        try:
            self.plans.tick(self.owner)
        except ApiError as error:
            logger.warning("lemon_schedule_blocked status=%s", error.status)
        with self.engine.connect() as connection:
            batches = runs.active(connection, self.scope, (*ACTIVE, "unknown"))
        for batch in batches:
            if self.stopping.is_set():
                return
            if batch["phase"] in ("queued", "discovering"):
                self.jobs.discover(batch)
                return
            rows = self.jobs.reconcile(batch)
            pending = next((v for v in rows if v["status"] == "queued"), None)
            if pending:
                self.jobs.execute(batch, pending)
                return
