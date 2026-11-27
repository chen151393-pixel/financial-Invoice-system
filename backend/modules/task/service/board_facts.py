"""判定任务当前节点所需的事实（合同归档、最新通知、报关资料、回签合同、来源是否变化）。

开票跟进任务台与工作台节点分布共用，保证两处的节点计数一致。只读。
"""

from collections import defaultdict

from ..dao import (
    declaration_document_dao,
    document_dao,
    event_dao,
    notification_dao,
    signed_contract_dao,
    supplier_task_dao,
    task_line_dao,
)
from ..mapper import document_mapper, notification_mapper, task_mapper
from ..policy.board_policy import current_node
from .basis_guard import CHANGED, changed_task_ids


def board_facts(connection, rows, *, node_only=False, node_facts=None):
    """批量读取判定节点所需的事实：合同归档、最新通知、报关资料、回签合同与来源是否变化。"""
    if not rows:
        return {}
    task_ids = [row["id"] for row in rows]
    lines = (
        task_line_dao.orders_by_tasks(connection, task_ids)
        if node_only
        else task_line_dao.by_tasks(connection, task_ids)
    )
    own = defaultdict(list)
    for line in lines:
        own[line["task_id"]].append(line)
    if node_facts is not None:
        result = {row["id"]: {**node_facts[row["id"]], "lines": own[row["id"]]} for row in rows}
        return _page_guards(connection, rows, lines, result)
    archived = document_dao.archived_orders(connection, task_ids)
    latest = notification_dao.latest_by_tasks(connection, task_ids)
    order_ids = sorted({line["purchase_order_id"] for line in lines})
    signed = (
        signed_contract_dao.saved_orders(connection, order_ids)
        if node_only
        else signed_contract_dao.by_orders(connection, order_ids)
    )
    declarations = declaration_document_dao.by_declarations(
        connection, sorted({row["customs_declaration_id"] for row in rows}), statuses_only=node_only
    )
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
            completion.missing,
        )
        result[row["id"]] = {
            "lines": own[row["id"]],
            "steps": steps,
            "node": current_node(steps),
            "missing": completion.missing,
            "blocked": "",
            "notice_status": notice["status"] if notice else None,
            "notice_id": notice["id"] if notice else None,
            "record_block": "",
        }
    return result if node_only else _page_guards(connection, rows, lines, result)


def _page_guards(connection, rows, lines, result):
    """计数时不需要来源与通知范围；当前页展示时仍实时校验，提交时仍按原入口重新校验。"""
    scopes = (
        event_dao.notification_scopes(
            connection,
            [row["id"] for row in supplier_task_dao.expand(connection, rows, all_statuses=True)],
        )
        if any(fact["notice_id"] for fact in result.values())
        else []
    )
    merged_notice_ids = {
        member["notificationId"]
        for event in scopes
        if event["details"] and len(event["details"].get("members", [])) > 1
        for member in event["details"]["members"]
    }
    changed = changed_task_ids(connection, lines)
    for task_id, fact in result.items():
        fact["blocked"] = CHANGED if task_id in changed else ""
        fact["record_block"] = (
            "该通知已按供应商合并，请从合并详情统一登记" if fact["notice_id"] in merged_notice_ids else ""
        )
    return result
