"""NS 定时计划：单据范围、下一页判定与批次汇总（纯函数）。

一个计划批次按单据类型从第一页起沿 nextCursor 串行执行；每页是一条 sync_ns_runs 记录，结果只存这一份。
页级 failed 表示本页任何关联组都未提交（多为账户锁被手动同步占用或 NS 列表读取暂时失败），
间隔后按同一游标重新排队，次数有上限；结果待核实（unknown/interrupted）立即停止，不自动重试。
"""

from datetime import timedelta, timezone

from .lemon_batch_policy import LABELS

# 单据类型 → (sync_runs.source, 中文名称)；报关单保存时自动补齐关联子采购和母采购单。
KINDS = {
    "customs-declarations": ("ns_customs", "报关单"),
    "sub-purchase-orders": ("ns_purchase", "子采购单"),
}
KIND_HINTS = {
    "customs-declarations": "按创建日期回扫报关单，并自动补齐关联子采购单、母采购单与关联依据",
    "sub-purchase-orders": "按创建日期回扫子采购单，补齐其所属报关单与母采购单",
}
ACTIVE = ("queued", "running")
# 分页状态的短标签（表格徽标用）；手动按批保存页面仍使用 ns_run_vo 的完整说明。
PAGE_LABELS = {
    "running": "执行中",
    "completed": "已保存",
    "partial": "部分失败",
    "interrupted": "已中断",
    "failed": "未写入",
    "unknown": "结果待核实",
}
FIRST_CURSOR = {"afterId": "0", "throughId": None, "offset": 0}
PAGE_LIMIT = 20
MAX_ATTEMPTS = 5
RETRY_AFTER = timedelta(seconds=60)
DEFAULT_PLAN = {
    "revision": 0,
    "enabled": False,
    "nextRunAt": None,
    "kinds": ["customs-declarations"],
    "times": ["02:00"],
    "lookbackDays": 30,
    "pausedReason": None,
}
PAUSED_UNKNOWN = "上次计划批次存在结果待核实的分页，计划已自动暂停；请先核对本地已保存单据，再重新启用"
PAUSED_ADMIN = "计划保存人已不是系统管理员，计划已自动暂停；请由管理员重新保存并启用"


def page_state(row, executing=frozenset()):
    """running 只在本进程正在执行时算执行中，否则结果待核实（沿用单 API worker 约束）。"""
    if row["status"] == "running" and row["request_id"] not in executing:
        return "unknown"
    return row["status"]


def next_step(pages, executing, now):
    """返回下一步：execute（附游标与偏移）、wait 或 finish（附批次阶段与说明）。"""
    if not pages:
        return {"action": "execute", "cursor": dict(FIRST_CURSOR), "offset": 0}
    last = pages[-1]
    state = page_state(last, executing)
    if state == "running":
        return {"action": "wait"}
    if state in ("unknown", "interrupted"):
        return {
            "action": "finish",
            "phase": "unknown",
            "message": "存在结果待核实的分页，已停止后续分页，不自动重试",
        }
    request = last["request"]
    if state == "failed":
        attempts = 0
        for row in reversed(pages):
            if row["status"] != "failed" or row["request"] != request:
                break
            attempts += 1
        if attempts >= MAX_ATTEMPTS:
            saved = any(row["status"] in ("completed", "partial") for row in pages)
            return {
                "action": "finish",
                "phase": "partial" if saved else "failed",
                "message": f"同一分页连续 {attempts} 次未能执行，已停止；最后原因：{last['error'] or '未知'}",
            }
        updated = last["updated_at"]
        if updated.tzinfo is not None:
            updated = updated.astimezone(timezone.utc).replace(tzinfo=None)
        if now - updated < RETRY_AFTER:
            return {"action": "wait"}
        return {"action": "execute", "cursor": request.get("cursor"), "offset": request["offset"]}
    result = last["result"] or {}
    if result.get("hasMore"):
        cursor = result.get("nextCursor")
        if not cursor or cursor == request.get("cursor"):
            return {
                "action": "finish",
                "phase": "partial",
                "message": "NS 后续分页游标缺失或未推进，已停止，未读完范围",
            }
        return {"action": "execute", "cursor": cursor, "offset": request["offset"] + request["limit"]}
    partial = any(row["status"] == "partial" for row in pages)
    return {
        "action": "finish",
        "phase": "partial" if partial else "completed",
        "message": "范围内全部分页已处理，存在失败或待核实单据，请查看分页明细"
        if partial
        else "范围内全部分页已处理完成；本地已有单据按 NS 身份更新、补齐",
    }


def summary(pages):
    """按已结束分页的实际保存结果汇总；新增/更新含随报关补齐的子采购单。"""
    counts = dict.fromkeys(("fetched", "created", "updated", "failed", "skipped"), 0)
    for row in pages:
        result = row["result"] or {}
        if row["status"] not in ("completed", "partial", "interrupted") or not result:
            continue
        counts["fetched"] += result.get("count", 0)
        storage = result.get("storage") or {}
        for section in ("customs", "purchase"):
            counts["created"] += (storage.get(section) or {}).get("created", 0)
            counts["updated"] += (storage.get(section) or {}).get("updated", 0)
        batch = (result.get("batch") or {}).get("counts") or {}
        counts["failed"] += batch.get("failed", 0)
        counts["skipped"] += batch.get("skipped", 0)
    return counts


def phase_label(phase):
    return LABELS[phase]
