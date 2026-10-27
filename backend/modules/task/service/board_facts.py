"""判定任务当前节点所需的事实（合同归档、最新通知、报关资料、回签合同、来源是否变化）。

开票跟进任务台与工作台节点分布共用，保证两处的节点计数一致。只读。
"""

from collections import defaultdict

from ..dao import (
    declaration_document_dao,
    document_dao,
    notification_dao,
    signed_contract_dao,
    task_line_dao,
)
from ..mapper import document_mapper, notification_mapper, task_mapper
from ..policy.board_policy import current_node
from .basis_guard import CHANGED, changed_task_ids


def board_facts(connection, rows):
    """批量读取判定节点所需的事实：合同归档、最新通知、报关资料、回签合同与来源是否变化。"""
    if not rows:
        return {}
    task_ids = [row["id"] for row in rows]
    lines = task_line_dao.by_tasks(connection, task_ids)
    own = defaultdict(list)
    for line in lines:
        own[line["task_id"]].append(line)
    archived = document_dao.archived_orders(connection, task_ids)
    latest = notification_dao.latest_by_tasks(connection, task_ids)
    signed = signed_contract_dao.by_orders(connection, sorted({line["purchase_order_id"] for line in lines}))
    declarations = declaration_document_dao.by_declarations(
        connection, sorted({row["customs_declaration_id"] for row in rows})
    )
    changed = changed_task_ids(connection, lines)
    result = {}
    for row in rows:
        order_ids = sorted({line["purchase_order_id"] for line in own[row["id"]]})
        saved = archived.get(row["id"], set())
        notice = latest.get(row["id"])
        completion = document_mapper.completion_of(
            order_ids, saved, declarations.get(row["customs_declaration_id"], {}), signed
        )
        steps = task_mapper.steps(
            row["status"],
            bool(order_ids) and set(order_ids) <= saved,
            bool(notice and notice["status"] == "sent"),
            notification_mapper.status_label(notice),
            completion.reason,
        )
        result[row["id"]] = {
            "lines": own[row["id"]],
            "steps": steps,
            "node": current_node(steps),
            "missing": completion.missing,
            "blocked": CHANGED if row["id"] in changed else "",
        }
    return result
