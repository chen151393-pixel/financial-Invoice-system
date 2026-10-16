"""发票版本只追加，当前投影单独更新。"""

from sqlalchemy import func, insert, select, update

from ..entity import headers, versions


def append(connection, values, now):
    revision = (
        connection.scalar(
            select(func.max(versions.c.revision)).where(versions.c.invoice_id == values["invoice_id"])
        )
        or 0
    ) + 1
    return connection.execute(
        insert(versions).values(**values, revision=revision, created_at=now, updated_at=now)
    ).inserted_primary_key[0]


def project(connection, invoice_id, values, now):
    connection.execute(update(headers).where(headers.c.id == invoice_id).values(**values, updated_at=now))


def by_ids(connection, ids):
    return (
        {
            r["id"]: dict(r)
            for r in connection.execute(select(versions).where(versions.c.id.in_(ids))).mappings()
        }
        if ids
        else {}
    )
