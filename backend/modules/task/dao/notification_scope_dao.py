"""从本模块追加式事件读取合并通知成员，不推断或改写发送状态。"""

from . import event_dao, supplier_task_dao, task_dao


def scopes(connection, task_id):
    return scopes_by_tasks(connection, [task_id]).get(task_id, [])


def scopes_by_tasks(connection, task_ids):
    """每种供应商身份只展开一次；包含已被替代任务，保留原通知的固定成员证据。"""
    rows = task_dao.by_ids(connection, sorted(set(task_ids)))
    anchors = supplier_task_dao.expand(connection, rows, all_statuses=True)
    identities = {row["id"]: supplier_task_dao.identity(row) for row in anchors}
    by_identity = {}
    for event in event_dao.notification_scopes(connection, list(identities)):
        if event["details"]:
            by_identity.setdefault(identities[event["task_id"]], []).append(event["details"])
    return {row["id"]: by_identity.get(supplier_task_dao.identity(row), []) for row in rows}


def find_scope(connection, task_id, notification_id=None):
    return match_scope(scopes(connection, task_id), task_id, notification_id)


def match_scope(values, task_id, notification_id=None):
    """从已批量读取的证据中按原有顺序匹配，不推断通知状态。"""
    return next(
        (
            scope
            for scope in values
            if any(
                member["taskId"] == task_id
                and (
                    notification_id is None
                    or scope["notificationId"] == notification_id
                    or member["notificationId"] == notification_id
                )
                for member in scope.get("members", [])
            )
        ),
        None,
    )


def roots_for_tasks(connection, task_ids):
    found = {}
    values = scopes_by_tasks(connection, task_ids)
    selected = set(task_ids)
    for task_id in dict.fromkeys(task_ids):
        for scope in values.get(task_id, []):
            if any(member["taskId"] in selected for member in scope.get("members", [])):
                found[scope["notificationId"]] = scope
    return list(found)
