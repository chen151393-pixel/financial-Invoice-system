"""消费已提交的合同归档队列；失败保留原因，重启接续尚未完成的只读下载。"""

import logging
from datetime import UTC, datetime
from threading import Event, Thread

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import contract_job_dao
from .contract_lock import BUSY_REASON, contract_lock

logger = logging.getLogger(__name__)


class ContractWorker:
    def __init__(self, engine, documents):
        self.engine, self.documents = engine, documents
        self.stopping = Event()
        self.thread = None

    def start(self):
        self.stopping.clear()
        self.thread = Thread(target=self._run, name="contract-archive", daemon=True)
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
                # 后台线程的隔离边界：记录异常，保留持久队列，不能因单次故障永久停止消费。
                logger.exception("合同归档队列处理异常，未完成记录将在下次检查时恢复")
            self.stopping.wait(2)

    def run_once(self):
        # 多进程部署只允许一个消费者；锁连接不持有事务，审核不等待网络下载。
        with contract_lock(self.engine, "worker") as acquired:
            if not acquired:
                return
            with self.engine.connect() as connection:
                jobs = contract_job_dao.pending(connection)
            for job in jobs:
                if self.stopping.is_set():
                    break
                self._prepare(job)

    def _prepare(self, job):
        try:
            self.documents.prepare(job["task_id"], job["purchase_order_id"], job["actor"])
        except ApiError as error:
            if error.message == BUSY_REASON:
                return
            self._fail(job, error.message)
        except SQLAlchemyError:
            # 数据库暂不可用时不丢失队列；下次循环重读持久状态。
            logger.exception("合同归档数据库暂不可用，作业 %s 保留待处理", job["id"])
        except Exception:
            logger.exception("合同归档作业 %s 发生异常", job["id"])
            self._fail(job, "合同自动归档发生异常，请联系管理员检查日志后手动重试")

    def _fail(self, job, message):
        with transaction(self.engine) as connection:
            contract_job_dao.fail(connection, job["id"], message, datetime.now(UTC).replace(tzinfo=None))
        logger.warning("合同自动归档失败，作业 %s：%s", job["id"], message)
