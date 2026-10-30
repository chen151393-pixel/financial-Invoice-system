"""NS 定时计划、计划批次与分页记录响应；不返回 NS 原始单据内容。"""

from ..policy.lemon_batch_policy import INTERRUPTED
from ..policy.ns_plan_policy import ACTIVE, DEFAULT_PLAN, KINDS, PAGE_LABELS, page_state, phase_label
from .lemon_batch_vo import iso


def plan_view(row):
    if not row:
        return dict(DEFAULT_PLAN)
    config = row["configuration"]
    return {
        "revision": row["revision"],
        "enabled": row["enabled"],
        "nextRunAt": iso(row["next_run_at"]),
        "kinds": config["kinds"],
        "times": config["times"],
        "lookbackDays": config["lookbackDays"],
        "pausedReason": config.get("pausedReason"),
    }


def batch_view(row, pages=None, executing=frozenset(), progress=None):
    config = row["configuration"] or {}
    view = {
        "requestId": row["request_id"],
        "kind": config.get("kind"),
        "kindLabel": KINDS.get(config.get("kind"), ("", "未知单据"))[1],
        "phase": row["phase"],
        "label": phase_label(row["phase"]),
        "trigger": row["trigger_type"],
        "startDate": config.get("startDate"),
        "endDate": config.get("endDate"),
        "createdAt": iso(row["started_at"]),
        "finishedAt": iso(row["finished_at"]),
        "message": row["message"],
        "fetched": row["fetched_count"],
        "created": row["created_count"],
        "updated": row["updated_count"],
        "failed": row["failed_count"],
    }
    if pages is not None:
        view["pages"] = [page_view(index, page, executing, progress) for index, page in enumerate(pages, 1)]
        view["poll"] = row["phase"] in ACTIVE
    return view


def page_view(index, row, executing, progress):
    status = page_state(row, executing)
    result = row["result"] or {}
    counts = (result.get("batch") or {}).get("counts") or {}
    return {
        "index": index,
        "requestId": row["request_id"],
        "status": status,
        "statusLabel": PAGE_LABELS[status],
        "count": result.get("count"),
        "saved": counts.get("saved", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "unknown": counts.get("unknown", 0),
        "failures": [
            {key: item.get(key) for key in ("id", "number", "status", "reason")}
            for item in (result.get("batch") or {}).get("items", [])
            if item.get("status") in ("failed", "unknown")
        ],
        # 进程中断留下的 running 记录没有错误原因，说明为何待核实。
        "error": row["error"] or (INTERRUPTED if status == "unknown" else None),
        "progress": progress if status == "running" and progress else None,
        "createdAt": iso(row["created_at"]),
        "updatedAt": iso(row["updated_at"]),
    }
