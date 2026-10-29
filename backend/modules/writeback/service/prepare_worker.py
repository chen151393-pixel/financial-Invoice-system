"""补偿扫描、只读查询与自动写入；单批有界，异常留待下一轮。"""

import logging
import threading

from backend.core.errors import ApiError

from ..dao import task_dao
from .queue_service import now

logger = logging.getLogger(__name__)


class PrepareWorker:
    def __init__(self, tasks, queries, *, enabled=False, executor=None):
        self.tasks, self.queries, self.enabled = tasks, queries, enabled
        # 写入开关关闭时不传 executor，后台不会尝试任何 NS 写入。
        self.executor = executor
        self.stop_event, self.thread, self.cursor = threading.Event(), None, 0

    def start(self):
        if (self.enabled or self.executor) and self.thread is None:
            self.thread = threading.Thread(target=self._run, name="writeback-prepare", daemon=True)
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=60)

    def tick(self):
        if self.enabled:
            self.cursor = self.tasks.scan(self.cursor)
            with self.tasks.engine.connect() as connection:
                rows = task_dao.pending(connection, self.tasks.account, now())
            for row in rows:
                if self.stop_event.is_set():
                    break
                try:
                    self.queries.refresh(row["id"], row["revision"], "system")
                except ApiError:
                    logger.info("准备任务 %s 本轮未完成查询，将按状态重查", row["id"])
        if self.executor and not self.stop_event.is_set():
            self.executor.run_ready()

    def _run(self):
        while not self.stop_event.wait(10):
            try:
                self.tick()
            except Exception:
                # 后台线程不能静默退出；不记录 NS 凭据或响应原文。
                logger.exception("回写准备扫描失败，本轮已停止")
