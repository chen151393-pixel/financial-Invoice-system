"""任务、任务行、状态历史与步骤的展示转换；金额与数量保持 Decimal 原值转为字符串。"""

from datetime import UTC

from ..policy.task_policy import LINE_STATUS_LABELS, STATUS_LABELS, STATUS_REASONS, event_label
from ..vo.task_vo import TaskCounts, TaskEvent, TaskLine, TaskStep, TaskSummary

UNKNOWN_SUPPLIER = "供应商待确认"
UNKNOWN_COMPANY = "采购公司待确认"


def iso(value):
    return value.replace(tzinfo=UTC).isoformat() if value else None


def text(value):
    if value is None:
        return ""
    # Decimal 去掉尾随零但不使用科学计数法，与审核页显示一致。
    return format(value.normalize(), "f") if hasattr(value, "normalize") else str(value)


def expected_total(lines):
    """全部任务行应开金额都已知时返回合计，否则为空（不以部分金额冒充总额）。"""
    amounts = [line["expected_amount"] for line in lines]
    return text(sum(amounts)) if amounts and all(amount is not None for amount in amounts) else None


def order_numbers(lines, names):
    order_ids = sorted({line["purchase_order_id"] for line in lines})
    return sorted(names["orders"].get(order_id) or "单号缺失" for order_id in order_ids)


def summary(task, lines, names):
    supplier = names["suppliers"].get(task["supplier_id"]) or {}
    return TaskSummary(
        id=str(task["id"]),
        account=task["ns_account"],
        recordNumber=task["record_no"] or "",
        supplier=supplier.get("name") or UNKNOWN_SUPPLIER,
        company=names["companies"].get(task["company_id"]) or UNKNOWN_COMPANY,
        currency=task["currency"] or "",
        status=task["status"],
        statusLabel=STATUS_LABELS[task["status"]],
        reason=STATUS_REASONS[task["status"]],
        createdAt=iso(task["created_at"]),
        reviewRevision=task["review_revision"],
        orderNumbers=order_numbers(lines, names),
        lineCount=len(lines),
        expectedAmount=expected_total(lines),
    )


def counts(status_counts):
    waiting = status_counts.get("documents_pending", 0) + status_counts.get("notify_pending", 0)
    open_count = (
        waiting + status_counts.get("awaiting_invoice", 0) + status_counts.get("partially_received", 0)
    )
    return TaskCounts(
        tasks=sum(status_counts.values()),
        awaitingInvoice=open_count,
        completed=status_counts.get("completed", 0),
        needsAttention=waiting,
    )


def lines(rows, names, currency):
    result = []
    for row in rows:
        item = names["lines"].get(row["purchase_line_id"]) or {}
        result.append(
            TaskLine(
                id=str(row["id"]),
                order=names["orders"].get(row["purchase_order_id"]) or "",
                name=item.get("declaration_name") or item.get("item_name") or "",
                specification=item.get("specification") or "",
                quantity=text(row["expected_quantity"]),
                unit=row["unit"] or "",
                amount=text(row["expected_amount"]),
                currency=currency or "",
                receivedQuantity=text(row["received_quantity"]),
                receivedAmount=text(row["received_amount"]),
                status=row["status"],
                statusLabel=LINE_STATUS_LABELS[row["status"]],
            )
        )
    return result


def events(rows):
    return [
        TaskEvent(
            at=iso(row["occurred_at"]),
            actor=row["actor"],
            label=event_label(row["from_status"], row["to_status"]),
            reason=row["reason"] or "",
        )
        for row in rows
    ]


def steps(status, documents_ready, notification_sent, notification_label):
    """六个节点各按自身事实判断是否完成（发票可能先于合同或通知到达）；当前节点为第一个未完成的节点。"""
    received = status in ("partially_received", "completed")
    completed = status == "completed"
    nodes = [
        ("财务审核", "审核已通过", True),
        ("资料准备", "原件已备齐" if documents_ready else "保存子采购合同到共享盘", documents_ready),
        ("通知供应商", notification_label, notification_sent),
        ("等待收票", "已收到发票" if received else "等待供应商开票", received),
        ("发票比对", "全部任务行已结束" if completed else "收票后在发票比对页审核", completed),
        ("完成", "已完成" if completed else "尚未完成", completed),
    ]
    live = status not in ("superseded", "completed")
    current = next((index for index, node in enumerate(nodes) if not node[2]), None) if live else None
    return [
        TaskStep(
            label=label,
            description=description,
            state="done" if done else "current" if index == current else "waiting",
        )
        for index, (label, description, done) in enumerate(nodes)
    ]
