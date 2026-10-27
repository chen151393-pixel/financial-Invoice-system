"""进项发票分布统计：按月张数（最近 6 个月）、票面展示状态、柠檬云账套，口径与列表筛选一致。"""

from datetime import date

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import header_dao
from ..policy.invoice_status_policy import LABELS
from ..vo.invoice_stats_vo import AccountCount, InvoiceStats, MonthCount, StatusCount

MONTHS = 6


def _month_window(last):
    """以 last 所在月为终点的连续 MONTHS 个月（YYYY-MM），按时间正序。"""
    year, month = last.year, last.month
    months = []
    for _ in range(MONTHS):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return list(reversed(months))


class InvoiceStatsService:
    def __init__(self, engine):
        self.engine = engine

    def stats(self, query, today=None):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        try:
            with self.engine.connect() as connection:
                statuses = header_dao.status_counts(connection, query)
                accounts = header_dao.account_counts(connection, query)
                dates = header_dao.date_counts(connection, query)
        except SQLAlchemyError:
            raise ApiError(503, "发票统计读取失败，请检查业务数据库及迁移状态") from None
        return InvoiceStats(
            total=sum(row["count"] for row in statuses),
            months=_months(dates, query.date_to or today or date.today()),
            statuses=_statuses(statuses),
            accounts=[AccountCount(account=row["account"], count=row["count"]) for row in accounts],
        )


def _months(rows, fallback):
    # 终点取筛选结果中最新的开票月份；无发票时取筛选截止日或今天所在月
    last = max((row["date"] for row in rows), default=fallback)
    window = _month_window(last)
    counts = dict.fromkeys(window, 0)
    for row in rows:
        key = f"{row['date'].year:04d}-{row['date'].month:02d}"
        if key in counts:
            counts[key] += row["count"]
    return [MonthCount(month=key, count=value) for key, value in counts.items()]


def _statuses(rows):
    # 与列表的展示状态一致：正常或已被红冲但金额为负的归为红字发票
    counts = dict.fromkeys(LABELS, 0)
    for row in rows:
        key = row["status"]
        if key in ("normal", "red_offset") and row["negative"]:
            key = "red_letter"
        counts[key if key in counts else "unknown"] += row["count"]
    return [StatusCount(key=key, label=LABELS[key], count=value) for key, value in counts.items()]
