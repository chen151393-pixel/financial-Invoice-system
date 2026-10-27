"""近 14 天同步情况：汇总 NS 批次、后台同步批次与柠檬云手动拉票的执行结果，按北京时间逐日统计。"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import lemon_run_dao, ns_run_dao, sync_run_dao
from ..policy.sync_health_policy import (
    BATCH_OUTCOMES,
    BATCH_SOURCES,
    LABELS,
    MANUAL_OUTCOMES,
    NS_KINDS,
    NS_OUTCOMES,
    ROWS,
    day_status,
)
from ..vo.sync_health_vo import HealthDay, HealthRow, SyncHealth

BUSINESS_ZONE = timezone(timedelta(hours=8))
DAYS = 14


def _local_date(at):
    # 运行记录时间以 UTC 存储（无时区）
    moment = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    return moment.astimezone(BUSINESS_ZONE).date().isoformat()


class SyncHealthService:
    def __init__(self, engine):
        self.engine = engine

    def health(self, now=None):
        now = now or datetime.now(timezone.utc)
        today = now.astimezone(BUSINESS_ZONE).date()
        first = today - timedelta(days=DAYS - 1)
        start = datetime.combine(first, datetime.min.time(), BUSINESS_ZONE).astimezone(timezone.utc)
        start = start.replace(tzinfo=None)
        try:
            with self.engine.connect() as connection:
                ns = ns_run_dao.since(connection, start)
                batches = sync_run_dao.since(connection, start)
                manual = lemon_run_dao.manual_since(connection, start)
        except SQLAlchemyError:
            raise ApiError(503, "同步记录读取失败，请检查业务数据库及迁移状态") from None
        outcomes = defaultdict(list)
        for row in ns:
            key, outcome = NS_KINDS.get(row["kind"]), NS_OUTCOMES.get(row["status"])
            if key and outcome:
                outcomes[(key, _local_date(row["created_at"]))].append(outcome)
        for row in batches:
            key, outcome = BATCH_SOURCES.get(row["source"]), BATCH_OUTCOMES.get(row["phase"])
            if key and outcome:
                outcomes[(key, _local_date(row["started_at"]))].append(outcome)
        for row in manual:
            outcome = MANUAL_OUTCOMES.get(row["status"])
            if outcome:
                outcomes[("lemon", _local_date(row["created_at"]))].append(outcome)
        dates = [(first + timedelta(days=offset)).isoformat() for offset in range(DAYS)]
        rows = []
        for key, label in ROWS:
            days = []
            for day in dates:
                items = outcomes.get((key, day), [])
                status = day_status(items)
                days.append(
                    HealthDay(
                        date=day,
                        status=status,
                        label=LABELS[status],
                        runs=len(items),
                        failed=sum(1 for item in items if item == "failed"),
                    )
                )
            rows.append(HealthRow(key=key, label=label, days=days))
        return SyncHealth(dates=dates, rows=rows)
