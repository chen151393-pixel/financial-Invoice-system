"""同步记录行转为响应对象；不查询数据库。"""

from ..vo.access_vo import SyncRun


def utc_text(value):
    """数据库存无时区的 UTC 时间，接口统一输出带 Z 的 ISO 8601 文本。"""
    return value.isoformat(timespec="seconds") + "Z" if value else None


def sync_run(row):
    if row is None:
        return None
    return SyncRun(
        id=row["id"],
        trigger=row["trigger"],
        status=row["status"],
        departments=row["departments"],
        usersAdded=row["users_added"],
        usersUpdated=row["users_updated"],
        usersDeactivated=row["users_deactivated"],
        error=row["error"],
        startedAt=utc_text(row["started_at"]),
        finishedAt=utc_text(row["finished_at"]),
    )
