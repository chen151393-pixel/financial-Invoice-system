"""后台常驻消费循环：数据库命名锁保证同一数据库一次只有一个消费者（柠檬云与 NS 计划共用）。"""

import hashlib
import logging
from threading import Event, Thread

from sqlalchemy.exc import SQLAlchemyError

from backend.core import named_lock

logger = logging.getLogger(__name__)


class ScheduledWorker:
    """子类设置 lock_prefix、thread_name、log_name 并实现 _consume()；每轮间隔 2 秒。"""

    lock_prefix = ""
    thread_name = ""
    log_name = ""

    def __init__(self, engine):
        self.engine = engine
        self.stopping, self.thread = Event(), None

    def start(self):
        self.stopping.clear()
        self.thread = Thread(target=self._run, name=self.thread_name, daemon=True)
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
                logger.error("%s_failed type=%s", self.log_name, type(error).__name__)
            self.stopping.wait(2)

    def run_once(self):
        name = hashlib.sha256(f"{self.lock_prefix}:{self.engine.url.database}".encode()).hexdigest()
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
        raise NotImplementedError
