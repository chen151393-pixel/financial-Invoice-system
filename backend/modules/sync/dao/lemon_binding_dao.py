"""绑定记录读写；条件更新防止重复向上游提交。"""

from datetime import datetime, timezone

from sqlalchemy import insert, select, update

from ..entity.lemon_binding import lemon_bindings as table


def get(connection, scope):
    row = connection.execute(select(table).where(table.c.scope_key == scope)).mappings().first()
    return dict(row) if row else None


def prepare(connection, scope, owner, mobile):
    row = get(connection, scope)
    if not row:
        connection.execute(
            insert(table).values(scope_key=scope, owner=owner, mobile=mobile, status="unbound")
        )
    elif row["status"] == "unbound":
        connection.execute(
            update(table)
            .where(table.c.scope_key == scope, table.c.status == "unbound")
            .values(
                mobile=mobile,
                updated_at=datetime.now(timezone.utc),
            )
        )


def transition(connection, scope, before, after, mobile=None):
    now = datetime.now(timezone.utc)
    values = {"status": after, "updated_at": now}
    if after == "bound":
        values["verified_at"] = now
    conditions = [table.c.mobile == mobile] if mobile is not None else []
    return (
        connection.execute(
            update(table)
            .where(
                table.c.scope_key == scope,
                table.c.status.in_(before),
                *conditions,
            )
            .values(**values)
        ).rowcount
        == 1
    )
