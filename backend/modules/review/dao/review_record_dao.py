"""审核记录：有效审核查询、新增、替代、历史。"""

from sqlalchemy import func, insert, select, update

from ..entity import records


def active_by_declarations(connection, declaration_ids):
    if not declaration_ids:
        return {}
    query = select(records).where(
        records.c.customs_declaration_id.in_(declaration_ids), records.c.status == "active"
    )
    return {row["customs_declaration_id"]: dict(row) for row in connection.execute(query).mappings()}


def active(connection, declaration_id, *, lock=False):
    query = select(records).where(
        records.c.customs_declaration_id == declaration_id, records.c.status == "active"
    )
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def max_revision(connection, declaration_id):
    query = select(func.max(records.c.revision)).where(records.c.customs_declaration_id == declaration_id)
    return connection.execute(query).scalar() or 0


def supersede(connection, review_id, now):
    connection.execute(
        update(records).where(records.c.id == review_id).values(status="superseded", updated_at=now)
    )


def insert_record(connection, values, now):
    return connection.execute(
        insert(records).values(status="active", created_at=now, updated_at=now, **values)
    ).inserted_primary_key[0]


def history(connection, declaration_id):
    query = (
        select(records)
        .where(records.c.customs_declaration_id == declaration_id)
        .order_by(records.c.revision.desc())
    )
    return [dict(row) for row in connection.execute(query).mappings()]
