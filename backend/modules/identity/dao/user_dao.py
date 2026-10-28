"""飞书人员副本、所属部门与个人角色。"""

from sqlalchemy import delete, insert, select, update

from ..entity import user_departments, user_roles, users


def get(connection, pk, *, lock=False):
    query = select(users).where(users.c.id == pk)
    if lock:
        query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def by_user_id(connection, user_id):
    row = connection.execute(select(users).where(users.c.user_id == user_id)).mappings().first()
    return dict(row) if row else None


def all_users(connection):
    query = select(users).order_by(users.c.active.desc(), users.c.name, users.c.id)
    return [dict(row) for row in connection.execute(query).mappings()]


def departments_by_user(connection, user_pks=None):
    query = select(user_departments.c.user_id, user_departments.c.department_id)
    if user_pks is not None:
        query = query.where(user_departments.c.user_id.in_(user_pks))
    result = {}
    for row in connection.execute(query):
        result.setdefault(row.user_id, set()).add(row.department_id)
    return result


def roles_by_user(connection, user_pks=None):
    query = select(user_roles.c.user_id, user_roles.c.role)
    if user_pks is not None:
        query = query.where(user_roles.c.user_id.in_(user_pks))
    result = {}
    for row in connection.execute(query):
        result.setdefault(row.user_id, set()).add(row.role)
    return result


def save(connection, values, now):
    """按飞书 user_id 新增或更新人员；返回 (本地主键, 是否新增, 是否有变化)。"""
    row = by_user_id(connection, values["user_id"])
    fields = {
        key: values[key] for key in ("open_id", "union_id", "name", "avatar_url", "active", "inactive_reason")
    }
    if row is None:
        result = connection.execute(
            insert(users).values(
                user_id=values["user_id"], synced_at=now, created_at=now, updated_at=now, **fields
            )
        )
        return result.inserted_primary_key[0], True, True
    changed = any(row[key] != value for key, value in fields.items())
    connection.execute(
        update(users).where(users.c.id == row["id"]).values(synced_at=now, updated_at=now, **fields)
    )
    return row["id"], False, changed


def replace_departments(connection, user_pk, department_ids, now):
    """整体替换人员所属部门；返回是否有变化。"""
    current = departments_by_user(connection, [user_pk]).get(user_pk, set())
    if current == set(department_ids):
        return False
    connection.execute(delete(user_departments).where(user_departments.c.user_id == user_pk))
    for department_id in sorted(department_ids):
        connection.execute(
            insert(user_departments).values(
                user_id=user_pk, department_id=department_id, created_at=now, updated_at=now
            )
        )
    return True


def deactivate_except(connection, keep_pks, reason, now):
    """本次同步未出现的在用人员改为不可登录；返回人数。"""
    query = select(users.c.id).where(users.c.active.is_(True))
    pks = [pk for pk in connection.execute(query).scalars() if pk not in keep_pks]
    if pks:
        connection.execute(
            update(users)
            .where(users.c.id.in_(pks))
            .values(active=False, inactive_reason=reason, updated_at=now)
        )
    return len(pks)


def replace_roles(connection, user_pk, roles, custom, actor, now):
    connection.execute(delete(user_roles).where(user_roles.c.user_id == user_pk))
    for role in roles:
        connection.execute(
            insert(user_roles).values(
                user_id=user_pk, role=role, granted_by=actor, created_at=now, updated_at=now
            )
        )
    connection.execute(update(users).where(users.c.id == user_pk).values(custom_roles=custom, updated_at=now))


def touch_login(connection, user_pk, now):
    connection.execute(update(users).where(users.c.id == user_pk).values(last_login_at=now))
