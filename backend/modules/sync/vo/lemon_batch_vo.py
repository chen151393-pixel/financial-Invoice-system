"""后台同步响应；隐藏绑定摘要和内部配置。"""

from collections import defaultdict

from ..policy.lemon_batch_policy import ACTIVE, INTERRUPTED, LABELS, retry_allowed, shard_state, summary


def iso(value):
    return value.isoformat() + "Z" if value else None


def batch_view(row, shards=None, executing=frozenset()):
    config = row["configuration"] or {}
    view = {
        "requestId": row["request_id"],
        "phase": row["phase"],
        "label": LABELS[row["phase"]],
        "trigger": row["trigger_type"],
        "startDate": config.get("startDate"),
        "endDate": config.get("endDate"),
        "businessTypes": config.get("businessTypes", []),
        "accountMode": config.get("accountMode"),
        "createdAt": iso(row["started_at"]),
        "finishedAt": iso(row["finished_at"]),
        "message": row["message"],
        "fetched": row["fetched_count"],
        "created": row["created_count"],
        "updated": row["updated_count"],
        "failed": row["failed_count"],
        "retry": {
            "allowed": retry_allowed(row),
            "reason": "仅重新提交明确失败的日期分片；结果待核实的分片不能重试",
        },
    }
    if shards is not None:
        accounts = defaultdict(list)
        for shard in shards:
            accounts[shard["asid"]].append(shard)
        view["accounts"] = [account_view(asid, rows, executing) for asid, rows in accounts.items()]
        view["poll"] = row["phase"] in ACTIVE
    return view


def account_view(asid, rows, executing=frozenset()):
    phase, counts = summary(rows, executing)
    leaves = [v for v in rows if v["status"] != "split"]
    return {
        "asid": asid,
        "name": rows[0]["account_name"],
        "phase": phase,
        "label": LABELS[phase],
        "counts": counts,
        "completed": sum(v["status"] == "completed" for v in leaves),
        "total": len(leaves),
        "windows": [
            {
                "startDate": v["start_date"].isoformat(),
                "endDate": v["end_date"].isoformat(),
                "label": LABELS[shard_state(v, executing)],
                "error": INTERRUPTED if shard_state(v, executing) == "unknown" else v["error"],
                "requestId": v["request_id"],
            }
            for v in leaves
        ],
    }


def plan_view(row):
    return (
        {
            "revision": row["revision"],
            "enabled": row["enabled"],
            "nextRunAt": iso(row["next_run_at"]),
            **{k: v for k, v in row["configuration"].items() if k != "bindingKey"},
        }
        if row
        else {
            "revision": 0,
            "enabled": False,
            "nextRunAt": None,
            "accountMode": "all",
            "accountIds": [],
            "excludedIds": [],
            "businessTypes": [],
            "times": ["02:00"],
            "lookbackDays": 90,
        }
    )
