"""写入相关状态规则，供服务与视图共用。"""

from datetime import timedelta

# 已发出或已写入 NS 的任务：审核变化时不能转为失效，也不能重新查询，否则会丢掉待核实的写入事实。
WRITTEN_STATES = {"executing", "partial", "unknown", "applied"}
# 执行中超过该时长仍无结果，视为进程中断，允许人工核实后标记。
STUCK_AFTER = timedelta(minutes=10)


def stuck(task, request, stamp):
    return bool(
        task["state"] == "executing"
        and request
        and request["sent_at"]
        and request["sent_at"] < stamp - STUCK_AFTER
    )
