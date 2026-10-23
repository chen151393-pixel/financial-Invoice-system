"""按全局依据生成任务后继；相同依据复用，任何完成状态的任务都可以换版。"""

from datetime import datetime, timezone

from backend.modules.review.public import ApprovedLine

from ..dao import (
    contract_job_dao,
    declaration_document_dao,
    event_dao,
    supplier_setting_dao,
    task_dao,
    task_line_dao,
)
from ..policy.task_policy import group_key
from .task_status_service import change_status


def on_review_approved(connection, event):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    incoming = {line.purchase_line_id: line for line in event.lines}
    active = {
        line["purchase_line_id"]: line
        for line in task_line_dao.active_by_purchase_lines(connection, list(incoming))
    }
    changed_tasks = sorted(
        {
            old["task_id"]
            for key, old in active.items()
            if old["purchase_basis_id"] != incoming[key].purchase_basis_id
        }
    )
    previous = {t["id"]: t for t in task_dao.by_ids(connection, changed_tasks, lock=True)}
    replacements = {
        key: line for key, line in incoming.items() if key not in active or active[key]["task_id"] in previous
    }
    for old in task_line_dao.by_tasks(connection, changed_tasks):
        key = old["purchase_line_id"]
        if key not in replacements:
            task = previous[old["task_id"]]
            replacements[key] = ApprovedLine(
                review_line_id=old["review_line_id"],
                purchase_order_id=old["purchase_order_id"],
                purchase_line_id=key,
                supplier_id=task["supplier_id"],
                company_id=task["company_id"],
                order_no="",
                currency=task["currency"],
                quantity=old["expected_quantity"],
                unit=old["unit"],
                amount=old["expected_amount"],
                purchase_basis_id=old["purchase_basis_id"],
            )
    for task in previous.values():
        change_status(connection, task, "superseded", event.approved_by, "开票依据换版，生成后继任务", now)
    task_line_dao.supersede(connection, changed_tasks, now)
    # 供应商档案关闭通知的，不生成开票任务（2026-10-23 业务确认，只影响之后的审核）
    muted = supplier_setting_dao.disabled(
        connection, sorted({line.supplier_id for line in replacements.values() if line.supplier_id})
    )
    groups = {}
    for line in replacements.values():
        if line.supplier_id in muted:
            continue
        key = group_key(line.supplier_id, line.company_id, line.currency, line.purchase_order_id)
        groups.setdefault(key, []).append(line)
    for key, lines in groups.items():
        _create(connection, event, key, lines, now, changed_tasks)
    if groups:
        # 报关单、销售合同、发票按报关单各下载一份，由后台队列处理；已有记录（含已归档）不重复登记
        declaration_document_dao.ensure(
            connection,
            event.customs_declaration_id,
            event.ns_account,
            event.record_no,
            event.approved_by,
            now,
        )
    for task_id in sorted({old["task_id"] for key, old in active.items() if key not in replacements}):
        task = task_dao.get(connection, task_id)
        event_dao.append(
            connection,
            {
                "task_id": task_id,
                "from_status": task["status"],
                "to_status": task["status"],
                "reason": f"相同开票依据关联 {event.record_no or '报关单'} 第 {event.revision} 版审核，未增加应开额度",
                "actor": event.approved_by,
                "event_type": "evidence_linked",
                "details": {"reviewId": event.review_id, "recordNumber": event.record_no},
            },
            now,
        )


def _create(connection, event, key, lines, now, predecessors):
    first = lines[0]
    task_id = task_dao.insert_task(
        connection,
        {
            "review_id": event.review_id,
            "predecessor_task_ids": predecessors,
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
                "purchase_basis_id": line.purchase_basis_id,
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
    contract_job_dao.enqueue(
        connection, task_id, [line.purchase_order_id for line in lines], event.approved_by, now
    )
    return task_id
