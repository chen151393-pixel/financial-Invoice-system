"""财务计算后台消费者；只读本地来源，不调用 NS 或自动审核。"""

import hashlib
import logging
from threading import Event, Thread

from sqlalchemy.exc import SQLAlchemyError

from backend.core import named_lock, write_lock
from backend.core.errors import ApiError

logger = logging.getLogger(__name__)


class CalculationWorker:
    def __init__(self, calculations):
        self.calculations = calculations
        self.stopping = Event()
        self.thread = None

    def start(self):
        self.stopping.clear()
        self.thread = Thread(target=self._run, name="review-calculation", daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread is not None:
            self.thread.join()

    def _run(self):
        initialized = False
        while not self.stopping.is_set():
            try:
                if not initialized:
                    self.calculations.initialize()
                    initialized = True
                self.run_once()
            except Exception:
                # 线程隔离边界：记录故障，已提交队列保留，不能吞掉错误后永久停止消费。
                logger.exception("财务计算队列暂不可用，将继续重试")
            self.stopping.wait(2)

    def run_once(self):
        engine = self.calculations.engine
        name = hashlib.sha256(f"review-calculation:{engine.url.database}".encode()).hexdigest()
        with engine.connect() as connection:
            with connection.begin():
                acquired = named_lock.acquire(connection, name)
            if not acquired:
                return
            try:
                for job in self.calculations.pending():
                    if self.stopping.is_set():
                        break
                    try:
                        self.calculations.calculate(job)
                    except Exception as error:
                        if isinstance(error, ApiError) and error.code in (
                            write_lock.BUSY_CODE,
                            write_lock.CONFLICT_CODE,
                        ):
                            # 账本或行锁被其他写入短暂占用不是计算错误：不记失败，几秒后重算。
                            logger.warning("账本正忙，财务计算稍后自动重试，账套 %s", job["ns_account"])
                            self.calculations.defer(job)
                        else:
                            logger.exception("财务计算失败，将自动重试，账套 %s", job["ns_account"])
                            self.calculations.fail(job)
            finally:
                try:
                    with connection.begin():
                        named_lock.release(connection, name)
                except SQLAlchemyError:
                    connection.invalidate()
