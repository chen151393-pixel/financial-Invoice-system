"""供应商任务的展示汇总；金额保持 Decimal，流程按未完成成员中最早待办判定。"""

from decimal import Decimal

from ..vo.capability import Capability
from ..vo.task_vo import BoardItem, TaskStep
from .board_policy import NODE_LABELS
from .followup_policy import amounts
from .notification_group_policy import group_revision
from .stage_policy import STAGE_LABELS, task_stage
from .task_policy import STATUS_LABELS, STATUS_REASONS

NODE_STATUS = {
    "documents": "documents_pending",
    "notification": "notify_pending",
    "invoices": "awaiting_invoice",
    "comparison": "partially_received",
    "completion": "documents_incomplete",
    "done": "completed",
}


def summary(items, lines):
    first = items[0].model_copy(deep=True)
    first.id = min(items, key=lambda item: int(item.id)).id
    first.recordNumber = "、".join(dict.fromkeys(item.recordNumber for item in items if item.recordNumber))
    first.declarationNumber = "、".join(
        dict.fromkeys(item.declarationNumber for item in items if item.declarationNumber)
    )
    first.orderNumbers = sorted({number for item in items for number in item.orderNumbers})
    first.lineCount = sum(item.lineCount for item in items)
    first.createdAt = min(item.createdAt for item in items)
    first.predecessorTaskIds = sorted({value for item in items for value in item.predecessorTaskIds})
    for field in ("expectedAmount", "receivedAmount", "outstandingAmount"):
        values = [getattr(item, field) for item in items]
        setattr(
            first,
            field,
            str(sum((Decimal(value) for value in values), Decimal(0)))
            if all(value is not None for value in values)
            else None,
        )
    outstanding, percent, bar = amounts(lines)
    first.outstandingAmount = format(outstanding, "f") if outstanding is not None else None
    first.receiptPercent = format(percent.normalize(), "f") if percent is not None else None
    first.receiptBarPercent = format(bar.normalize(), "f") if bar is not None else None
    first.waitingLabel = min(items, key=lambda item: item.createdAt).waitingLabel
    contacted = [item for item in items if item.lastContactAt]
    if contacted:
        latest = max(contacted, key=lambda item: item.lastContactAt)
        first.lastContactAt, first.followupEmployee = latest.lastContactAt, latest.followupEmployee
    return first


def steps_and_node(items):
    result = []
    current = False
    for index, template in enumerate(items[0]):
        states = [steps[index].state for steps in items]
        state = (
            "done"
            if all(value == "done" for value in states)
            else "skipped"
            if all(value in ("done", "skipped") for value in states)
            else "current"
            if not current
            else "waiting"
        )
        if state == "current":
            current = True
        result.append(
            TaskStep(key=template.key, label=template.label, description=template.description, state=state)
        )
    result[1].description = (
        "子采购合同已全部归档" if result[1].state == "done" else "保存全部子采购合同到共享盘"
    )
    node = next((step.key for step in result if step.state == "current"), "done")
    return result, node


def capability(values):
    blocked = next((value.reason for value in values if not value.allowed), "")
    return Capability(allowed=all(value.allowed for value in values), reason=blocked or values[0].reason)


def apply_status(task, node):
    task.status = NODE_STATUS[node]
    task.statusLabel = STATUS_LABELS[task.status]
    task.reason = STATUS_REASONS[task.status]
    task.stage = task_stage(task.status) or ""
    task.stageLabel = STAGE_LABELS.get(task.stage, "")


def board_item(items, lines):
    merged = summary([item.task for item in items], lines)
    steps, node = steps_and_node([item.steps for item in items])
    apply_status(merged, node)
    missing = list(dict.fromkeys(name for item in items for name in item.missing))
    targets = [target for item in items for target in item.notifyTargets]
    steps[1].description = (
        "子采购合同已全部归档" if steps[1].state == "done" else "保存全部子采购合同到共享盘"
    )
    steps[2].description = "本供应商已全部通知" if steps[2].state == "done" else "待通知供应商"
    steps[-1].description = (
        "已完成" if node == "done" else ("尚缺：" + "、".join(missing) if missing else "发票收齐后任务完结")
    )
    return BoardItem(
        grouped=True,
        taskIds=[item.task.id for item in items],
        task=merged,
        steps=steps,
        currentNode=node,
        currentLabel=NODE_LABELS[node],
        nextAction=NODE_LABELS[node],
        blockedReason="；".join(dict.fromkeys(item.blockedReason for item in items if item.blockedReason)),
        missing=missing,
        notifyRecord=Capability(
            allowed=True, reason=f"本组可登记 {len(targets)} 个待通知任务，其余任务不在本次范围。"
        )
        if targets
        else capability([item.notifyRecord for item in items]),
        notifyTargets=targets,
        notifyScopeRevision=group_revision([(item.task.id, item.notifyScopeRevision) for item in items]),
    )
