"""后台消费者与每日调度；数据库命名锁保证一次只有一个消费者。"""

import hashlib
import logging
from threading import Event, Thread

from sqlalchemy.exc import SQLAlchemyError

from backend.core import named_lock
from backend.core.errors import ApiError

from ..dao import sync_run_dao as runs
from ..policy.lemon_batch_policy import ACTIVE

logger = logging.getLogger(__name__)


class LemonWorker:
    def __init__(self, plans, jobs):
        self.plans, self.jobs, self.engine = plans, jobs, jobs.engine
        self.owner = f"user:{jobs.accounts.binding.settings.admin_user}"
        self.scope = jobs.batches.scope(self.owner)
        self.stopping, self.thread = Event(), None

    def start(self):
        self.stopping.clear()
        self.thread = Thread(target=self._run, name="lemon-sync", daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join()

    def _run(self):
        while not self.stopping.is_set():
            try:
                self.run_once()
            except Exception as error:  # noqa: BLE001 -- 常驻线程隔离边界，不吞掉任务或自动重发
                # 消费循环的最后隔离边界：任务保留在库中，日志不含驱动或上游原始正文。
                logger.error("lemon_worker_failed type=%s", type(error).__name__)
            self.stopping.wait(2)

    def run_once(self):
        name = hashlib.sha256(f"lemon-worker:{self.engine.url.database}".encode()).hexdigest()
        with self.engine.connect() as lock:
            with lock.begin():
                acquired = named_lock.acquire(lock, name)
            if not acquired:
                return
            try:
                self._consume()
            finally:
                try:
                    with lock.begin():
                        named_lock.release(lock, name)
                except SQLAlchemyError:
                    lock.invalidate()

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
