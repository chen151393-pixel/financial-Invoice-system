"""预览快照和个人范围的数据访问，不决定同步及授权状态。"""

from sqlalchemy import delete, insert, select, update

from ..entity import directory_previews, user_sync_scopes


def create(connection, values, now):
    connection.execute(delete(directory_previews).where(directory_previews.c.expires_at < now))
    connection.execute(insert(directory_previews).values(**values, created_at=now, updated_at=now))


def get(connection, preview_id):
    row = (
        connection.execute(select(directory_previews).where(directory_previews.c.id == preview_id))
        .mappings()
        .first()
    )
    return dict(row) if row else None


def finish(connection, preview_id, result, now):
    connection.execute(
        update(directory_previews)
        .where(directory_previews.c.id == preview_id)
        .values(result=result, updated_at=now)
    )


def user_ids(connection):
    return set(connection.execute(select(user_sync_scopes.c.user_id)).scalars())


def replace_users(connection, ids, actor, now):
    connection.execute(delete(user_sync_scopes))
    for user_id in sorted(ids):
        connection.execute(
            insert(user_sync_scopes).values(user_id=user_id, created_by=actor, created_at=now, updated_at=now)
        )
