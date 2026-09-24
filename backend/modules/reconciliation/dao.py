"""所有审核SQL共用Service事务，唯一键及条件更新阻止重复或过期确认。"""

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from .entity import reviews, snapshots


def approved_sources(connection, owner):
    return list(
        connection.execute(
            select(reviews, snapshots.c.payload)
            .join(snapshots, snapshots.c.id == reviews.c.snapshot_id)
            .where(reviews.c.owner == owner, reviews.c.digest.is_not(None))
        ).mappings()
    )


def scope(owner, account, declaration_id):
    return (
        reviews.c.owner == owner,
        reviews.c.account == account,
        reviews.c.declaration_id == declaration_id,
    )


def head(connection, owner, account, declaration_id):
    where = scope(owner, account, declaration_id)
    row = connection.execute(select(reviews).where(*where)).mappings().first()
    if row is None:
        try:
            with connection.begin_nested():
                connection.execute(
                    insert(reviews).values(
                        owner=owner, account=account, declaration_id=declaration_id, revision=0
                    )
                )
        except IntegrityError:
            pass  # 同一报关单首次查询并发创建，唯一键胜出的记录即为共同审核头。
    return connection.execute(select(reviews).where(*where).with_for_update()).mappings().one()


def add_snapshot(connection, values):
    connection.execute(insert(snapshots).values(**values))


def snapshot(connection, snapshot_id, owner, account=None):
    return (
        connection.execute(
            select(snapshots).where(
                snapshots.c.id == snapshot_id,
                snapshots.c.owner == owner,
                *([snapshots.c.account == account] if account is not None else []),
            )
        )
        .mappings()
        .first()
    )


def approve(connection, preview, owner, now, note):
    return (
        connection.execute(
            update(reviews)
            .where(
                *scope(owner, preview["account"], preview["declaration_id"]),
                reviews.c.revision == preview["revision"],
            )
            .values(
                revision=preview["revision"] + 1,
                snapshot_id=preview["id"],
                digest=preview["digest"],
                reviewed_at=now,
                reviewed_by=owner,
                note=note,
            )
        ).rowcount
        == 1
    )
