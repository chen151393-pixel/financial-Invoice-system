"""手动 NS 分页记录投影为执行记录；数量沿用计划的已保存结果汇总。"""

from ..policy.ns_plan_policy import KINDS, page_state, phase_label, summary
from .lemon_batch_vo import iso
from .ns_plan_vo import page_view


def manual_view(row, executing, *, detail=False, progress=None):
    status = page_state(row, executing)
    phase = "unknown" if status == "interrupted" else status
    result = row["result"] or {}
    counts = summary([row])
    view = {
        "requestId": row["request_id"],
        "recordType": "manual",
        "kind": row["kind"],
        "kindLabel": KINDS[row["kind"]][1],
        "phase": phase,
        "label": phase_label(phase),
        "trigger": "manual",
        "startDate": row["request"].get("startDate"),
        "endDate": row["request"].get("endDate"),
        "createdAt": iso(row["created_at"]),
        "finishedAt": None if row["status"] == "running" else iso(row["updated_at"]),
        "message": row["error"] or result.get("message") or ("保存结果待核实" if phase == "unknown" else ""),
        **{key: counts[key] for key in ("fetched", "created", "updated", "failed")},
    }
    if detail:
        index = row["request"].get("offset", 0) // row["request"].get("limit", 20) + 1
        view["pages"] = [page_view(index, row, executing, progress)]
        view["poll"] = phase == "running"
    return view
