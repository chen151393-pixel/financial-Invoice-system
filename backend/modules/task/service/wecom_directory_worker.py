"""定期消费企微群目录队列；退出时先等待同步结束，再关闭 HTTP 客户端。"""

import logging
from threading import Event, Thread

logger = logging.getLogger(__name__)


class WecomDirectoryWorker:
    def __init__(self, service):
        self.service = service
        self.stopping = Event()
        self.thread = None

    def start(self):
        self.stopping.clear()
        self.thread = Thread(target=self._run, name="wecom-directory", daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread is not None:
            self.thread.join()

    def _run(self):
        while not self.stopping.is_set():
            try:
                self.service.run_once()
            except Exception:
                # 数据库故障不终止消费者，持久状态会在恢复连接后继续处理。
                logger.exception("企微群目录后台任务暂不可用，将在下次检查时恢复")
            self.stopping.wait(2)
