"""NS 定时计划后台消费者：到期入队并推进计划批次；常驻循环与数据库命名锁见 ScheduledWorker。"""

import logging

from backend.core.errors import ApiError

from .scheduled_worker import ScheduledWorker

logger = logging.getLogger(__name__)


class NsPlanWorker(ScheduledWorker):
    lock_prefix, thread_name, log_name = "ns-plan-worker", "ns-plan-sync", "ns_plan_worker"

    def __init__(self, plans, jobs):
        super().__init__(jobs.engine)
        self.plans, self.jobs = plans, jobs

    def _consume(self):
        try:
            self.plans.tick()
        except ApiError as error:
            logger.warning("ns_schedule_blocked status=%s", error.status)
        # 一轮最多推进若干页后释放命名锁，停止服务时不必等完整个范围。
        for _ in range(10):
            if self.stopping.is_set() or not self.jobs.step():
                return
