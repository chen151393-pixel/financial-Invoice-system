"""按人员计算生效角色：部门默认角色沿部门树向下继承，再与个人角色合并。

登录、每次请求的会话校验与权限管理页共用这一套计算。
"""

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import department_dao, directory_preview_dao, user_dao
from ..policy.department_policy import ancestors, subtree
from ..policy.role_policy import effective_roles


class DepartmentIndex:
    """一次读取的部门树快照，用于计算继承角色和部门路径。"""

    def __init__(self, departments, roles_by_department):
        self.by_id = {row["id"]: row for row in departments}
        self.by_open = {row["open_department_id"]: row for row in departments}
        self.parent_of = {row["open_department_id"]: row["parent_open_id"] for row in departments}
        self.roles_by_department = roles_by_department

    def inherited_roles(self, department_ids):
        roles = set()
        for department_id in department_ids:
            row = self.by_id.get(department_id)
            if row is None:
                continue
            for open_id in ancestors(row["open_department_id"], self.parent_of):
                roles |= self.roles_by_department.get(self.by_open[open_id]["id"], set())
        return roles

    def path(self, department_id):
        row = self.by_id.get(department_id)
        if row is None:
            return ""
        names = [
            self.by_open[open_id]["name"] for open_id in ancestors(row["open_department_id"], self.parent_of)
        ]
        return " / ".join(reversed(names))


def load_index(connection):
    return DepartmentIndex(
        department_dao.all_departments(connection), department_dao.roles_by_department(connection)
    )


def roles_for(index, user, department_ids, personal_roles):
    return effective_roles(index.inherited_roles(department_ids), personal_roles, user["custom_roles"])


class AccessReader:
    def __init__(self, engine):
        self.engine = engine

    def principal(self, connection, user_id):
        """(人员, 生效角色)；人员不存在时为 (None, [])。"""
        user = user_dao.by_user_id(connection, user_id)
        if user is None:
            return None, []
        departments = user_dao.departments_by_user(connection, [user["id"]]).get(user["id"], set())
        personal = user_dao.roles_by_user(connection, [user["id"]]).get(user["id"], set())
        index = load_index(connection)
        if not in_scope(connection, index, user, departments):
            user = {**user, "active": False, "inactive_reason": "已不在同步范围内"}
        return user, roles_for(index, user, departments, personal)

    def current(self, user_id):
        """会话校验用：返回 (人员, 生效角色)；数据库不可用时拒绝，而不是放行。"""
        try:
            with self.engine.connect() as connection:
                return self.principal(connection, user_id)
        except SQLAlchemyError:
            raise ApiError(503, "人员权限读取失败，请检查业务数据库") from None


def in_scope(connection, index, user, department_ids):
    if user["user_id"] in directory_preview_dao.user_ids(connection):
        return True
    roots = department_dao.scope_ids(connection)
    covered = subtree(
        [d["open_department_id"] for d in index.by_id.values() if d["id"] in roots and d["active"]],
        index.parent_of,
    )
    return any(index.by_id.get(pk, {}).get("open_department_id") in covered for pk in department_ids)
