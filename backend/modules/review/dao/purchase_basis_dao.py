"""开票依据查询、冻结与生命周期更新；只访问 review 表。"""

from sqlalchemy import func, insert, select, update

from ..entity import bases, lines


def current(connection, ids, *, lock=False):
    query = select(bases).where(bases.c.current_purchase_line_id.in_(ids)).order_by(bases.c.purchase_line_id)
    if lock:
        query = query.with_for_update()
    return {r["purchase_line_id"]: dict(r) for r in connection.execute(query).mappings()} if ids else {}


def by_ids(connection, ids):
    return (
        {r["id"]: dict(r) for r in connection.execute(select(bases).where(bases.c.id.in_(ids))).mappings()}
        if ids
        else {}
    )


def next_revision(connection, line_id):
    return (
        connection.scalar(select(func.max(bases.c.revision)).where(bases.c.purchase_line_id == line_id)) or 0
    ) + 1


def insert_basis(connection, values, now):
    return connection.execute(
        insert(bases).values(**values, created_at=now, updated_at=now)
    ).inserted_primary_key[0]


def set_status(connection, ids, status, now):
    if ids:
        connection.execute(update(bases).where(bases.c.id.in_(ids)).values(status=status, updated_at=now))


def required_declarations(connection, review_ids):
    query = (
        select(lines.c.review_id)
        .join(bases, bases.c.current_purchase_line_id == lines.c.purchase_line_id)
        .where(
            lines.c.review_id.in_(review_ids),
            (bases.c.status == "review_required") | bases.c.currency.is_(None),
        )
    )
    return set(connection.execute(query).scalars()) if review_ids else set()
