"""计算队列的原子请求、代次校验与重试持久化；不负责事务提交。"""

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..entity.calculation_job import calculation_jobs as jobs


def request(connection, account, now):
    values = dict(ns_account=account, requested_revision=1, updated_at=now)
    changes = dict(
        requested_revision=jobs.c.requested_revision + 1,
        attempts=0,
        retry_at=None,
        last_error="",
        updated_at=now,
    )
    if connection.dialect.name == "mysql":
        statement = mysql_insert(jobs).values(**values).on_duplicate_key_update(**changes)
    else:
        statement = (
            sqlite_insert(jobs)
            .values(**values)
            .on_conflict_do_update(index_elements=[jobs.c.ns_account], set_=changes)
        )
    connection.execute(statement)


def get(connection, account, *, lock=False):
    statement = select(jobs).where(jobs.c.ns_account == account)
    if lock:
        statement = statement.with_for_update()
    row = connection.execute(statement).mappings().first()
    return dict(row) if row else None


def set_key(connection, account, key, now):
    connection.execute(
        update(jobs).where(jobs.c.ns_account == account).values(calculation_key=key, updated_at=now)
    )


def pending(connection, now):
    return [
        dict(row)
        for row in connection.execute(
            select(jobs)
            .where(
                jobs.c.requested_revision > jobs.c.completed_revision,
                or_(jobs.c.retry_at.is_(None), jobs.c.retry_at <= now),
            )
            .order_by(jobs.c.updated_at, jobs.c.ns_account)
            .limit(10)
        ).mappings()
    ]


def accounts(connection):
    return list(connection.execute(select(jobs.c.ns_account).order_by(jobs.c.ns_account)).scalars())


def unfinished(connection):
    return list(
        connection.execute(
            select(jobs.c.ns_account).where(jobs.c.requested_revision != jobs.c.completed_revision)
        ).scalars()
    )


def complete(connection, job, now):
    connection.execute(
        update(jobs)
        .where(jobs.c.ns_account == job["ns_account"])
        .values(
            completed_revision=job["requested_revision"],
            attempts=0,
            retry_at=None,
            last_error="",
            updated_at=now,
        )
    )


def fail(connection, job, message, retry_at, now):
    connection.execute(
        update(jobs)
        .where(
            jobs.c.ns_account == job["ns_account"],
            jobs.c.requested_revision == job["requested_revision"],
            jobs.c.calculation_key == job["calculation_key"],
            jobs.c.completed_revision < job["requested_revision"],
        )
        .values(attempts=job["attempts"] + 1, last_error=message, retry_at=retry_at, updated_at=now)
    )
