"""企微目录 SQL；事务与同步策略由 Service 管理。"""

from datetime import UTC, datetime

from sqlalchemy import bindparam, insert, select, update
from sqlalchemy.exc import IntegrityError

from ..entity.wecom_directory import directories, groups


def get(connection, scope, *, lock=False):
    statement = select(directories).where(directories.c.scope == scope)
    if lock:
        statement = statement.with_for_update()
    row = connection.execute(statement).mappings().first()
    return dict(row) if row else None


def ensure(connection, scope, now):
    row = get(connection, scope, lock=True)
    if row:
        return row
    try:
        with connection.begin_nested():
            connection.execute(
                insert(directories).values(
                    scope=scope,
                    status="queued",
                    has_snapshot=False,
                    discovered=0,
                    completed=0,
                    total=None,
                    unavailable_count=0,
                    next_sync_at=now,
                    error="",
                    created_at=now,
                    updated_at=now,
                )
            )
    except IntegrityError:
        # 同时首次查询时只保留一份队列，唯一约束保护跨进程创建。
        if get(connection, scope, lock=True) is None:
            raise
    return get(connection, scope, lock=True)


def change(connection, directory_id, now, *, expected_token=None, **values):
    statement = update(directories).where(directories.c.id == directory_id)
    if expected_token is not None:
        statement = statement.where(directories.c.run_token == expected_token)
    return connection.execute(
        statement.values(
            **values,
            updated_at=now,
        )
    ).rowcount


def items(connection, directory_id):
    rows = connection.execute(
        select(groups).where(
            groups.c.directory_id == directory_id,
            groups.c.is_active.is_(True),
        )
    ).mappings()
    return [
        {
            "chatId": row["chat_id"],
            "groupName": row["group_name"],
            "userid": row["owner_userid"],
            "employee": row["owner_name"],
            "memberCount": row["member_count"],
            "createdAt": int(row["group_created_at"].replace(tzinfo=UTC).timestamp())
            if row["group_created_at"]
            else None,
        }
        for row in rows
    ]


def publish(connection, directory_id, catalog, now, next_sync_at):
    existing = dict(
        connection.execute(
            select(groups.c.chat_id, groups.c.id).where(
                groups.c.directory_id == directory_id,
            )
        ).all()
    )
    connection.execute(
        update(groups)
        .where(groups.c.directory_id == directory_id)
        .values(
            is_active=False,
            updated_at=now,
        )
    )
    additions, changes = [], []
    for item in catalog["items"]:
        values = {
            "group_name": item["groupName"],
            "owner_name": item["employee"],
            "owner_userid": item["userid"],
            "member_count": item["memberCount"],
            "group_created_at": datetime.fromtimestamp(item["createdAt"], UTC).replace(tzinfo=None)
            if item["createdAt"] is not None
            else None,
            "is_active": True,
            "updated_at": now,
        }
        if item["chatId"] in existing:
            changes.append({"_row_id": existing[item["chatId"]], **values})
        else:
            additions.append(
                {"directory_id": directory_id, "chat_id": item["chatId"], "created_at": now, **values}
            )
    if changes:
        connection.execute(
            update(groups)
            .where(groups.c.id == bindparam("_row_id"))
            .values({key: bindparam(key) for key in changes[0] if key != "_row_id"}),
            changes,
        )
    if additions:
        connection.execute(insert(groups), additions)
    change(
        connection,
        directory_id,
        now,
        status="ready",
        has_snapshot=True,
        synced_at=now,
        next_sync_at=next_sync_at,
        error="",
        unavailable_count=catalog["unavailableCount"],
    )
