"""每日定时计划的触发时间：配置按北京时间解释，存储与比较使用 UTC（柠檬云与 NS 计划共用）。"""

from datetime import datetime, timedelta, timezone

SHANGHAI = timezone(timedelta(hours=8))


def next_time(times, now):
    local = now.replace(tzinfo=timezone.utc).astimezone(SHANGHAI)
    for offset in (0, 1):
        for value in sorted(times):
            hour, minute = map(int, value.split(":"))
            candidate = datetime.combine(local.date() + timedelta(days=offset), datetime.min.time(), SHANGHAI)
            candidate = candidate.replace(hour=hour, minute=minute)
            if candidate > local:
                return candidate.astimezone(timezone.utc).replace(tzinfo=None)
    raise ValueError("每日执行时间不能为空")


def local_today(now):
    """UTC 时刻对应的北京时间日期，用于冻结回扫窗口。"""
    return now.replace(tzinfo=timezone.utc).astimezone(SHANGHAI).date()
