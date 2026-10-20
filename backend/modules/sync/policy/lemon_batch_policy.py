"""同步范围、分片及状态汇总；不把开票日期当作修改时间游标。"""

import hashlib
from datetime import datetime, timedelta, timezone

from backend.core.errors import ApiError

SHANGHAI = timezone(timedelta(hours=8))
ACTIVE = ("queued", "discovering", "running")
LABELS = {
    "queued": "等待执行",
    "discovering": "查询授权账套",
    "running": "执行中",
    "completed": "已完成",
    "partial": "部分成功",
    "failed": "失败",
    "unknown": "结果待核实",
    "split": "已拆分",
}


def binding_key(binding):
    return hashlib.sha256(f"{binding['id']}|{binding['scope_key']}|{binding['mobile']}".encode()).hexdigest()


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


def windows(start, end):
    while start <= end:
        finish = min(start + timedelta(days=30), end)
        yield start, finish
        start = finish + timedelta(days=1)


def selected_accounts(items, configuration):
    if configuration["accountMode"] == "all":
        chosen = [v for v in items if v["asid"] not in configuration["excludedIds"]]
    else:
        available = {v["asid"]: v for v in items}
        # 撤权账套保留为独立失败任务，不能被静默省略。
        chosen = [
            available.get(key, {"asid": key, "name": f"账套 {key}（当前未授权）"})
            for key in configuration["accountIds"]
        ]
    if not chosen:
        raise ApiError(409, "当前发现范围内没有可纳入的授权账套，请检查授权或排除设置")
    return chosen


INTERRUPTED = "执行曾中断，提交结果待核实；禁止直接重试"


def shard_state(row, executing=frozenset()):
    """分片展示状态。running 只在本进程正在执行时算执行中，否则提交结果待核实（沿用单 API worker 约束）。"""
    if row["status"] == "running" and row["request_id"] not in executing:
        return "unknown"
    return row["status"]


def summary(shards, executing=frozenset()):
    leaves = [row for row in shards if row["status"] != "split"]
    states = [shard_state(row, executing) for row in leaves]
    if any(v in ("queued", "running") for v in states):
        phase = "running"
    elif "unknown" in states:
        phase = "unknown"
    elif states and all(v == "completed" for v in states):
        phase = "completed"
    elif "completed" in states:
        phase = "partial"
    else:
        phase = "failed"
    counts = {
        key: sum((r["result"] or {}).get(key, 0) for r in leaves if r["status"] == "completed")
        for key in (
            "fetched",
            "created",
            "updated",
            "unchanged",
            "excluded",
            "completeDetails",
            "pendingDetails",
        )
    }
    return phase, counts


def retry_allowed(batch):
    return batch["phase"] in ("failed", "partial") and batch["failed_count"] > 0
