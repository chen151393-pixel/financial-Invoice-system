"""持久导入队列消费者；MySQL 命名锁使多个进程按上传顺序单消费者执行。"""

import hashlib
import logging
from threading import Event, Thread

from sqlalchemy.exc import SQLAlchemyError

from backend.core import named_lock

logger = logging.getLogger(__name__)


class CustomsImportWorker:
    def __init__(self, imports):
        self.imports = imports
        self.stopping = Event()
        self.thread = None

    def start(self):
        self.stopping.clear()
        self.thread = Thread(target=self._run, name="customs-import", daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread is not None:
            self.thread.join()

    def _run(self):
        while not self.stopping.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("海关导入队列暂不可用，未完成作业保留并稍后继续")
            self.stopping.wait(2)

    def run_once(self):
        engine = self.imports.engine
        if engine is None:
            return
        name = hashlib.sha256(f"customs-import:{engine.url.database}".encode()).hexdigest()
        with engine.connect() as connection:
            with connection.begin():
                acquired = named_lock.acquire(connection, name)
            if not acquired:
                return
            try:
                self.imports.process_next()
            finally:
                try:
                    with connection.begin():
                        named_lock.release(connection, name)
                except SQLAlchemyError:
                    connection.invalidate()
