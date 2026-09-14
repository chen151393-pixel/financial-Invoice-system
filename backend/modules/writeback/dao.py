"""回写数据访问：所有方法接受调用方连接，不创建或提交事务。"""

from sqlalchemy import delete, insert, select, update

from .entity import previews, target_locks


def get(connection, preview_id, owner, account):
    return (
        connection.execute(
            select(previews).where(
                previews.c.id == preview_id,
                previews.c.owner == owner,
                previews.c.account == account,
            )
        )
        .mappings()
        .first()
    )


def list_jobs(connection, owner, account):
    return (
        connection.execute(
            select(
                previews.c.id,
                previews.c.target,
                previews.c.operation,
                previews.c.expires,
                previews.c.state,
            )
            .where(previews.c.owner == owner, previews.c.account == account)
            .order_by(previews.c.created_at.desc(), previews.c.id)
            .limit(25)
        )
        .mappings()
        .all()
    )


def create(connection, values):
    connection.execute(insert(previews).values(**values))


def claim(connection, preview_id, owner, account, now):
    return connection.execute(
        update(previews)
        .where(
            previews.c.id == preview_id,
            previews.c.owner == owner,
            previews.c.account == account,
            previews.c.state == "preview",
            previews.c.expires > now,
        )
        .values(state="executing")
    ).rowcount


def lock_target(connection, account, target, preview_id):
    connection.execute(insert(target_locks).values(account=account, target=target, preview_id=preview_id))


def transition(connection, preview_id, owner, account, state, result):
    return connection.execute(
        update(previews)
        .where(
            previews.c.id == preview_id,
            previews.c.owner == owner,
            previews.c.account == account,
            previews.c.state == "executing",
        )
        .values(state=state, result=result)
    ).rowcount


def release_target(connection, preview_id):
    connection.execute(delete(target_locks).where(target_locks.c.preview_id == preview_id))


def executing(connection, account):
    return connection.execute(
        select(previews.c.id, previews.c.owner).where(
            previews.c.account == account,
            previews.c.state == "executing",
        )
    ).all()
