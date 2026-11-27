"""发送执行台账查询和条件更新；不决定状态、不提交事务。"""

from sqlalchemy import func, insert, or_, select, update

from ..entity.notification_delivery import deliveries
from ..entity.task_line import task_lines
from .notification_scope_dao import roots_for_tasks, scopes_by_tasks


def detail_by_tasks(connection, task_ids, statuses):
    """批量读取详情所需的历史与未决保护，仍覆盖同一采购行的全部历史任务。"""
    if not task_ids:
        return {}, set(), {}
    own = task_lines.alias("own")
    related = {}
    query = (
        select(own.c.task_id.label("owner_id"), task_lines.c.task_id)
        .select_from(own.join(task_lines, task_lines.c.purchase_line_id == own.c.purchase_line_id))
        .where(own.c.task_id.in_(task_ids))
        .distinct()
    )
    for row in connection.execute(query).mappings():
        related.setdefault(row["owner_id"], set()).add(row["task_id"])
    all_ids = set(task_ids).union(*(related.values()))
    scopes = scopes_by_tasks(connection, sorted(all_ids))

    def roots(ids):
        selected = set(ids)
        return {
            scope["notificationId"]
            for task_id in selected
            for scope in scopes.get(task_id, [])
            if any(member["taskId"] in selected for member in scope.get("members", []))
        }

    history_roots = {task_id: roots([task_id]) for task_id in task_ids}
    blocked_roots = {task_id: roots(related.get(task_id, ())) for task_id in task_ids}
    notification_ids = set().union(*history_roots.values(), *blocked_roots.values())
    query = select(deliveries).where(
        or_(deliveries.c.task_id.in_(sorted(all_ids)), deliveries.c.notification_id.in_(notification_ids))
    )
    by_task, by_notice = {}, {}
    for row in connection.execute(query.order_by(deliveries.c.id.desc())).mappings():
        value = dict(row)
        by_task.setdefault(row["task_id"], []).append(value)
        by_notice.setdefault(row["notification_id"], []).append(value)

    def find(ids, notices):
        found = {row["id"]: row for task_id in ids for row in by_task.get(task_id, [])}
        found.update({row["id"]: row for notice in notices for row in by_notice.get(notice, [])})
        return sorted(found.values(), key=lambda row: row["id"], reverse=True)

    history = {task_id: find([task_id], history_roots[task_id]) for task_id in task_ids}
    blocked = {
        task_id
        for task_id in task_ids
        if any(row["status"] in statuses for row in find(related.get(task_id, ()), blocked_roots[task_id]))
    }
    return history, blocked, scopes


def get(connection, delivery_id, *, lock=False):
    query = select(deliveries).where(deliveries.c.id == delivery_id)
    row = connection.execute(query.with_for_update() if lock else query).mappings().first()
    return dict(row) if row else None


def by_request(connection, request_id):
    row = (
        connection.execute(select(deliveries).where(deliveries.c.request_id == request_id)).mappings().first()
    )
    return dict(row) if row else None


def history(connection, task_id):
    return [
        dict(row)
        for row in connection.execute(
            select(deliveries)
            .where(
                or_(
                    deliveries.c.task_id == task_id,
                    deliveries.c.notification_id.in_(roots_for_tasks(connection, [task_id])),
                )
            )
            .order_by(deliveries.c.id.desc())
        ).mappings()
    ]


def overlapping(connection, task_id, statuses):
    own = select(task_lines.c.purchase_line_id).where(task_lines.c.task_id == task_id)
    related = list(
        connection.execute(
            select(task_lines.c.task_id).where(task_lines.c.purchase_line_id.in_(own))
        ).scalars()
    )
    query = select(deliveries).where(
        or_(
            deliveries.c.task_id.in_(related),
            deliveries.c.notification_id.in_(roots_for_tasks(connection, related)),
        ),
        deliveries.c.status.in_(statuses),
    )
    return [dict(row) for row in connection.execute(query).mappings()]


def insert_delivery(connection, values, now):
    return connection.execute(
        insert(deliveries).values(**values, created_at=now, updated_at=now)
    ).inserted_primary_key[0]


def update_delivery(connection, delivery_id, values, now):
    connection.execute(
        update(deliveries).where(deliveries.c.id == delivery_id).values(**values, updated_at=now)
    )


def count_group(connection, corp_id, chat_id, start, end, statuses):
    return connection.execute(
        select(func.count())
        .select_from(deliveries)
        .where(
            deliveries.c.corp_id == corp_id,
            deliveries.c.chat_id == chat_id,
            deliveries.c.created_at >= start,
            deliveries.c.created_at < end,
            deliveries.c.status.in_(statuses),
        )
    ).scalar_one()
