"""收票进度：订阅 matching 的 AllocationChanged，按已通过分配的汇总更新任务行与任务状态。

- 订阅方在发布方事务中执行，不开启新事务、不调用外部系统；失败时整个比对操作回滚。
- 任务行：已收数量金额为缓存，以事件携带的已通过分配合计为准（数据库设计第 6.1 节）。
- 任务：全部有效任务行结束 → completed；有收票 → partially_received；
  分配取消后没有收票 → 退回收票前节点（已登记通知 → 等待开票；合同已归档 → 待通知；否则待保存合同）。
"""

from datetime import datetime, timezone

from ..dao import document_dao, notification_dao, task_dao, task_line_dao
from ..policy.task_policy import line_progress, task_progress
from .task_status_service import change_status


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def on_allocation_changed(connection, event):
    now = _now()
    receipts = {receipt.purchase_line_id: receipt for receipt in event.receipts}
    found = task_line_dao.active_by_purchase_lines(connection, list(receipts))
    # 加锁顺序：任务 → 任务行（后端规则第 7 节）。
    tasks = {
        task["id"]: task
        for task in task_dao.by_ids(connection, sorted({line["task_id"] for line in found}), lock=True)
    }
    lines = task_line_dao.active_by_purchase_lines(connection, list(receipts), lock=True)
    for line in lines:
        receipt = receipts[line["purchase_line_id"]]
        apply_receipt(connection, line, receipt.quantity, receipt.amount, receipt.closed, now)
    for task in tasks.values():
        refresh_task(connection, task, event.actor, event.reason, now)


def apply_receipt(connection, line, quantity, amount, closed, now):
    status, over, closed_with_difference = line_progress(
        line["expected_quantity"], line["expected_amount"], quantity, amount, closed
    )
    task_line_dao.update_progress(
        connection,
        line["id"],
        {
            "received_quantity": quantity,
            "received_amount": amount,
            "status": status,
            "over_invoiced": over,
            "closed_with_difference": closed_with_difference,
        },
        now,
    )


def base_status(connection, task_id, order_ids):
    """收票前的节点：由通知与合同的实际记录得出，不保存额外状态。"""
    latest = notification_dao.latest(connection, task_id)
    if latest and latest["status"] == "sent":
        return "awaiting_invoice"
    archived = {
        doc["purchase_order_id"]
        for doc in document_dao.by_task(connection, task_id)
        if doc["status"] == "archived"
    }
    return "notify_pending" if order_ids and set(order_ids) <= archived else "documents_pending"


def refresh_task(connection, task, actor, reason, now):
    """调用方须已锁定任务；按有效任务行状态推进或退回任务状态。"""
    if task["status"] == "superseded":
        return
    lines = [
        line for line in task_line_dao.by_tasks(connection, [task["id"]]) if line["status"] != "superseded"
    ]
    order_ids = sorted({line["purchase_order_id"] for line in lines})
    target = task_progress([line["status"] for line in lines], base_status(connection, task["id"], order_ids))
    if target != task["status"]:
        change_status(connection, task, target, actor, reason, now)
