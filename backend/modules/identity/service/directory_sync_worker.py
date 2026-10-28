"""每日定时同步飞书部门与成员；与手动“立即同步”共用 DirectorySyncService。"""

import logging
from datetime import timedelta
from threading import Event, Thread

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

logger = logging.getLogger(__name__)


class DirectorySyncWorker:
    def __init__(self, service, *, interval=timedelta(hours=24), check_seconds=3600, first_delay=60):
        self.service, self.interval = service, interval
        self.check_seconds, self.first_delay = check_seconds, first_delay
        self.stopping = Event()
        self.thread = None

    def start(self):
        if not self.service.feishu.configured:
            return
        self.stopping.clear()
        self.thread = Thread(target=self._run, name="identity-directory-sync", daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=30)

    def _run(self):
        delay = self.first_delay
        while not self.stopping.wait(delay):
            delay = self.check_seconds
            try:
                if self.service.due(self.interval):
                    self.service.sync("schedule", "system")
            except (ApiError, SQLAlchemyError) as failure:
                # 原因已写入同步记录；日志不带飞书返回原文。
                logger.warning("identity_directory_sync_failed type=%s", type(failure).__name__)
