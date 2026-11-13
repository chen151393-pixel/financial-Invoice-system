"""复用 task_events 保存人员快照与交接，不增加任务归属表。"""

from sqlalchemy import select

from ..entity import events, tasks
from . import event_dao


def snapshot(owner):
    return (
        {"recordId": owner["id"], "memberId": owner["member_id"], "memberName": owner["member_name"]}
        if owner
        else None
    )


def append(
    connection, task_id, owner, effective_at, reason, actor, now, *, transfer=False, previous_member_id=None
):
    status = connection.execute(select(tasks.c.status).where(tasks.c.id == task_id)).scalar_one()
    event_dao.append(
        connection,
        {
            "task_id": task_id,
            "from_status": status,
            "to_status": status,
            "event_type": "owner_transferred" if transfer else "owner_assigned",
            "details": {"owner": snapshot(owner), "fromMemberId": previous_member_id},
            "reason": reason,
            "actor": actor,
        },
        now,
        occurred_at=effective_at,
    )


def _attribution(row):
    owner = (row["details"] or {}).get("owner") or {}
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "owner_version_id": owner.get("recordId"),
        "member_id": owner.get("memberId"),
        "member_name": owner.get("memberName"),
        "effective_at": row["occurred_at"],
        "reason": row["reason"],
        "actor": row["actor"],
    }


def timeline(connection, task_id):
    query = select(events).where(events.c.task_id == task_id).order_by(events.c.occurred_at, events.c.id)
    return [
        _attribution(dict(row))
        for row in connection.execute(query).mappings()
        if "owner" in (row["details"] or {})
    ]


def open_tasks(connection, supplier_id, company_id):
    return [
        dict(row)
        for row in connection.execute(
            select(tasks)
            .where(
                tasks.c.supplier_id == supplier_id,
                tasks.c.company_id == company_id,
                tasks.c.status.not_in(("completed", "superseded")),
            )
            .order_by(tasks.c.id)
        ).mappings()
    ]


def at_time(connection, task_id, at):
    """从业务发生时之前的最后一条人员事件读取归属；未知历史不追溯当前分工。"""
    query = (
        select(events)
        .where(events.c.task_id == task_id, events.c.occurred_at <= at)
        .order_by(events.c.occurred_at.desc(), events.c.id.desc())
    )
    for row in connection.execute(query).mappings():
        if "owner" in (row["details"] or {}):
            return _attribution(dict(row))
    return None
