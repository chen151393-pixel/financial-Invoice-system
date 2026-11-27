"""任务详情的批量只读装载；详情与供应商合并详情共用，不缓存跨请求业务状态。"""

from collections import defaultdict

from ..dao import (
    contract_job_dao,
    declaration_document_dao,
    document_dao,
    event_dao,
    notification_dao,
    notification_delivery_dao,
    signed_contract_dao,
    supplier_group_dao,
    task_line_dao,
)
from ..policy.delivery_policy import ACTIVE
from .basis_guard import CHANGED, changed_task_ids


def read_details(connection, rows):
    ids = [row["id"] for row in rows]
    lines = task_line_dao.by_tasks(connection, ids)
    documents = document_dao.by_tasks(connection, ids)
    own_lines, own_documents = defaultdict(list), defaultdict(list)
    for line in lines:
        own_lines[line["task_id"]].append(line)
    for doc in documents:
        own_documents[doc["task_id"]].append(doc)
    changed = changed_task_ids(connection, lines)
    declarations = declaration_document_dao.by_declarations(
        connection, sorted({row["customs_declaration_id"] for row in rows})
    )
    jobs = contract_job_dao.by_tasks(connection, ids)
    notifications = notification_dao.history_by_tasks(connection, ids)
    contacts = notification_dao.latest_sent_by_tasks(connection, ids)
    deliveries, blocked, scopes = notification_delivery_dao.detail_by_tasks(connection, ids, ACTIVE)
    events = event_dao.by_tasks(connection, ids)
    bindings = supplier_group_dao.by_suppliers(
        connection, sorted({row["supplier_id"] for row in rows if row["supplier_id"]})
    )
    signed = signed_contract_dao.by_orders(connection, sorted({line["purchase_order_id"] for line in lines}))
    return {
        "lines": lines,
        "documents": documents,
        "latest": {task_id: values[0] for task_id, values in notifications.items()},
        "signed": signed,
        "scopes": scopes,
        "tasks": {
            row["id"]: {
                "task": row,
                "lines": own_lines[row["id"]],
                "documents": own_documents[row["id"]],
                "basis_reason": "任务已被新审核版本替代"
                if row["status"] == "superseded"
                else CHANGED
                if row["id"] in changed
                else "",
                "declaration_documents": declarations.get(row["customs_declaration_id"], {}),
                "contract_jobs": jobs.get(row["id"], {}),
                "notifications": notifications.get(row["id"], []),
                "contact": contacts.get(row["id"]),
                "deliveries": deliveries.get(row["id"], []),
                "delivery_blocked": row["id"] in blocked,
                "events": events.get(row["id"], []),
                "binding": bindings.get(row["supplier_id"]),
            }
            for row in rows
        },
    }
