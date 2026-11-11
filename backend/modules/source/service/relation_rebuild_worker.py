"""启动时补算旧版关联；版本随事务保存，重启可续跑，失败重试而不标记完成。"""

import logging
from threading import Event, Thread

logger = logging.getLogger(__name__)


class RelationRebuildWorker:
    def __init__(self, service):
        self.service = service
        self.stopping = Event()
        self.thread = None

    def start(self):
        self.stopping.clear()
        self.thread = Thread(target=self._run, name="source-relation-rebuild", daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread is not None:
            self.thread.join()

    def _run(self):
        while not self.stopping.is_set():
            try:
                results = self.service.rebuild(stopping=self.stopping.is_set)
                for result in results:
                    if result["status"] != "current":
                        logger.info("source_local_relation_rebuild %s", result)
                return
            except Exception:
                # 线程隔离边界；事务回滚，已完成的版本标记允许下一次只处理剩余单据。
                logger.exception("本地关联重建未完成，将重试；不会请求 NS")
            self.stopping.wait(5)
