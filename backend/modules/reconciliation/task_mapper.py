"""任务行与展示对象的纯转换；金额保持来源字符串。"""

import json
from datetime import UTC, datetime

from .task_vo import TaskCounts, TaskSummary


def summary(row):
    payload = json.loads(row["payload"])
    superseded = row["status"] == "superseded"
    return TaskSummary(
        id=row["id"],
        account=row["account"],
        recordNumber=row["record_number"],
        supplier=row["supplier"],
        company=row["company"],
        currency=row["currency"],
        status=row["status"],
        statusLabel="已被新审核版本替代"
        if superseded
        else "等待供应商开票"
        if row["status"] == "awaiting_invoice"
        else ("待通知供应商" if row["status"] == "notify_pending" else "待保存子采购合同"),
        reason="请查看该报关单最新审核生成的任务。"
        if superseded
        else "已人工登记发送通知，等待供应商开票；尚无企微渠道回执。"
        if row["status"] == "awaiting_invoice"
        else (
            "子采购合同已保存到共享盘，等待通知供应商开票。"
            if row["status"] == "notify_pending"
            else "财务审核已通过，将子采购合同保存到共享盘后通知供应商。"
        ),
        createdAt=datetime.fromtimestamp(row["created_at"], UTC).isoformat(),
        reviewRevision=row["review_revision"],
        snapshotId=row["snapshot_id"],
        orderNumbers=[order["number"] or "单号缺失" for order in payload["orders"]],
        lineCount=len(payload["lines"]),
    )


def counts(status_counts):
    current = status_counts.get("documents_pending", 0) + status_counts.get("notify_pending", 0)
    return TaskCounts(
        tasks=sum(status_counts.values()),
        awaitingInvoice=current + status_counts.get("awaiting_invoice", 0),
        needsAttention=current,
    )
