"""飞书部门副本、同步范围与部门默认角色。"""

from sqlalchemy import delete, insert, select, update

from ..entity import department_roles, departments, sync_scopes


def all_departments(connection):
    query = select(departments).order_by(departments.c.name, departments.c.id)
    return [dict(row) for row in connection.execute(query).mappings()]


def save_all(connection, items, now):
    """按飞书读取结果保存部门；本次未读到的部门标为停用。返回保存的部门数。"""
    existing = {row["open_department_id"]: row for row in connection.execute(select(departments)).mappings()}
    seen = set()
    for item in items:
        open_id = item["open_department_id"]
        seen.add(open_id)
        values = {"parent_open_id": item["parent_open_id"], "name": item["name"], "active": True}
        row = existing.get(open_id)
        if row is None:
            connection.execute(
                insert(departments).values(
                    open_department_id=open_id, synced_at=now, created_at=now, updated_at=now, **values
                )
            )
        else:
            connection.execute(
                update(departments)
                .where(departments.c.id == row["id"])
                .values(synced_at=now, updated_at=now, **values)
            )
    missing = [row["id"] for key, row in existing.items() if key not in seen and row["active"]]
    if missing:
        connection.execute(
            update(departments).where(departments.c.id.in_(missing)).values(active=False, updated_at=now)
        )
    return len(seen)


def scope_ids(connection):
    return set(connection.execute(select(sync_scopes.c.department_id)).scalars())


def replace_scopes(connection, department_ids, actor, now):
    connection.execute(delete(sync_scopes))
    for department_id in sorted(department_ids):
        connection.execute(
            insert(sync_scopes).values(
                department_id=department_id, created_by=actor, created_at=now, updated_at=now
            )
        )


def roles_by_department(connection):
    result = {}
    for row in connection.execute(select(department_roles.c.department_id, department_roles.c.role)):
        result.setdefault(row.department_id, set()).add(row.role)
    return result


def replace_roles(connection, department_id, roles, actor, now):
    connection.execute(delete(department_roles).where(department_roles.c.department_id == department_id))
    for role in roles:
        connection.execute(
            insert(department_roles).values(
                department_id=department_id, role=role, granted_by=actor, created_at=now, updated_at=now
            )
        )
