"""柠檬云拉票记录 DAO：手动拉票与后台分片同表，不决定业务状态。"""

from datetime import datetime, timezone

from sqlalchemy import insert, select, update

from ..entity.lemon_run import lemon_runs as table

# 排队和已拆分的分片还不是（或已不再是）一次真实拉取，“最近一次拉票”不展示它们。
PULLED = ("running", "completed", "failed")


def get(connection, scope, request_id):
    row = (
        connection.execute(select(table).where(table.c.scope_key == scope, table.c.request_id == request_id))
        .mappings()
        .first()
    )
    return dict(row) if row else None


def latest(connection, scope):
    row = (
        connection.execute(
            select(table)
            .where(table.c.scope_key == scope, table.c.status.in_(PULLED))
            .order_by(table.c.id.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def running(connection, scope, *, asid=None, manual_only=False):
    conditions = [table.c.scope_key == scope, table.c.status == "running"]
    if asid is not None:
        conditions.append(table.c.asid == asid)
    if manual_only:
        conditions.append(table.c.run_id.is_(None))
    return connection.scalar(select(table.c.id).where(*conditions).limit(1))


def create(connection, values):
    connection.execute(insert(table).values(**values))


def create_shards(connection, values):
    if values:
        connection.execute(insert(table), values)


def batch_shards(connection, run_id):
    query = select(table).where(table.c.run_id == run_id).order_by(table.c.id)
    return [dict(row) for row in connection.execute(query).mappings()]


def lock_shard(connection, shard_id):
    row = connection.execute(select(table).where(table.c.id == shard_id).with_for_update()).mappings().first()
    return dict(row) if row else None


def claim(connection, scope, request_id):
    """排队分片转为执行中；返回受影响行数，非 1 表示已被领取或状态已变化。"""
    return connection.execute(
        update(table)
        .where(table.c.scope_key == scope, table.c.request_id == request_id, table.c.status == "queued")
        .values(status="running", updated_at=datetime.now(timezone.utc))
    ).rowcount


def mark(connection, shard_id, status, *, expected, error=None):
    return connection.execute(
        update(table)
        .where(table.c.id == shard_id, table.c.status == expected)
        .values(status=status, error=error, updated_at=datetime.now(timezone.utc))
    ).rowcount


def finish(connection, scope, request_id, status, *, result=None, error=None):
    values = {"status": status, "error": error, "updated_at": datetime.now(timezone.utc)}
    if result is not None:
        values["result"] = result
    return connection.execute(
        update(table)
        .where(table.c.scope_key == scope, table.c.request_id == request_id, table.c.status == "running")
        .values(**values)
    ).rowcount
