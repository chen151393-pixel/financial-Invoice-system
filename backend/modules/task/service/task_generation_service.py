"""订阅 review 的 ReviewApproved：在审核事务中生成开票任务（数据库设计第 7 节第 3 步）。

- 新审核替代旧审核时，旧审核生成的未完成任务及其任务行改为 superseded；已完成的任务保留。
- 按 供应商 × 采购公司 × 币种 分组；同一子采购行已有有效任务行（其他报关单或已完成任务）时跳过。
- 订阅方在发布方事务中执行，不调用外部系统、不开启新事务；失败时整个审核回滚。
"""

from datetime import datetime, timezone

from ..dao import event_dao, task_dao, task_line_dao
from ..policy.task_policy import OPEN_STATUSES, group_key
from .task_status_service import change_status

SYSTEM = "system"


def on_review_approved(connection, event):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if event.superseded_review_id:
        _supersede(connection, event.superseded_review_id, event.revision, now)
    active = task_line_dao.active_purchase_lines(connection, [line.purchase_line_id for line in event.lines])
    groups = {}
    for line in event.lines:
        if line.purchase_line_id in active:
            continue
        key = group_key(line.supplier_id, line.company_id, line.currency, line.purchase_order_id)
        groups.setdefault(key, []).append(line)
    for key, lines in groups.items():
        _create(connection, event, key, lines, now)


def _supersede(connection, review_id, revision, now):
    previous = [
        task
        for task in task_dao.by_review(connection, review_id, lock=True)
        if task["status"] in OPEN_STATUSES
    ]
    for task in previous:
        change_status(connection, task, "superseded", SYSTEM, f"财务重新审核（第 {revision} 版）", now)
    task_line_dao.supersede(connection, [task["id"] for task in previous], now)


def _create(connection, event, key, lines, now):
    first = lines[0]
    task_id = task_dao.insert_task(
        connection,
        {
            "review_id": event.review_id,
            "review_revision": event.revision,
            "ns_account": event.ns_account,
            "customs_declaration_id": event.customs_declaration_id,
            "record_no": event.record_no,
            "supplier_id": first.supplier_id,
            "company_id": first.company_id,
            "currency": first.currency,
            "group_key": key,
            "status": "documents_pending",
        },
        now,
    )
    task_line_dao.insert_lines(
        connection,
        [
            {
                "task_id": task_id,
                "review_line_id": line.review_line_id,
                "purchase_order_id": line.purchase_order_id,
                "purchase_line_id": line.purchase_line_id,
                "expected_quantity": line.quantity,
                "unit": line.unit,
                "expected_amount": line.amount,
                "status": "open",
            }
            for line in lines
        ],
        now,
    )
    event_dao.append(
        connection,
        {
            "task_id": task_id,
            "from_status": None,
            "to_status": "documents_pending",
            "reason": f"财务审核通过（{event.record_no or '报关单'} 第 {event.revision} 版）",
            "actor": event.approved_by,
        },
        now,
    )
