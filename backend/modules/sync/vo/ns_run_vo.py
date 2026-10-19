"""NS 后台保存批次响应：只返回已持久化的状态与结果，执行中附带临时阶段进度。"""

STATUS_LABELS = {
    "running": "执行中",
    "completed": "本批已全部保存",
    "partial": "本批部分单据保存失败，请查看逐单结果",
    "interrupted": "本批已中断，请核实待核实单据后再继续",
    "failed": "本批未写入任何单据",
    "unknown": "结果待核实：请先核对本地已保存单据，不要直接重新拉取",
}


def run_view(row, *, active, progress=None):
    status = row["status"]
    if status == "running" and not active:
        # 当前进程没有在执行：服务重启或结束状态未能写入，不能推断已保存或未保存。
        status = "unknown"
    return {
        "requestId": row["request_id"],
        "kind": row["kind"],
        "request": row["request"],
        "status": status,
        "statusLabel": STATUS_LABELS[status],
        "progress": progress if status == "running" else None,
        "result": row["result"],
        "error": row["error"],
        "createdAt": row["created_at"].isoformat() if row.get("created_at") else None,
        "updatedAt": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }
