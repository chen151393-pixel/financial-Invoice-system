"""权限管理：同步范围、部门默认角色、个人角色；只有系统管理员可以操作。

人员与部门以飞书为准，这里不能新增人员或修改姓名、部门。
"""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import audit_dao, department_dao, directory_preview_dao, sync_run_dao, user_dao
from ..mapper.sync_run_mapper import sync_run, utc_text
from ..policy.department_policy import ancestors, subtree
from ..policy.login_policy import feishu_user_id
from ..policy.role_policy import ROLES, ordered, unknown_roles
from ..vo.access_vo import AccessOverview
from .access_reader import in_scope, load_index, roles_for


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _check_roles(roles):
    invalid = unknown_roles(roles)
    if invalid:
        raise ApiError(400, f"未知角色：{'、'.join(invalid)}")
    return ordered(roles)


class AccessService:
    def __init__(self, engine, identity, feishu):
        self.engine, self.identity, self.feishu = engine, identity, feishu

    def overview(self, actor):
        self.identity.require_manage(actor)
        try:
            with self.engine.connect() as connection:
                index = load_index(connection)
                scopes = department_dao.scope_ids(connection)
                explicit_users = directory_preview_dao.user_ids(connection)
                users = user_dao.all_users(connection)
                memberships = user_dao.departments_by_user(connection)
                personal = user_dao.roles_by_user(connection)
                last_run = sync_run_dao.latest(connection)
        except SQLAlchemyError:
            raise ApiError(503, "人员与权限读取失败，请检查业务数据库") from None
        active = [row for row in index.by_id.values() if row["active"]]
        parent_of = {row["open_department_id"]: row["parent_open_id"] for row in active}
        covered = subtree([row["open_department_id"] for row in active if row["id"] in scopes], parent_of)
        departments = sorted(
            (
                {
                    "id": row["id"],
                    "openDepartmentId": row["open_department_id"],
                    "name": row["name"],
                    "path": index.path(row["id"]),
                    "inScope": row["id"] in scopes,
                    "covered": row["open_department_id"] in covered,
                    "roles": ordered(index.roles_by_department.get(row["id"], set())),
                }
                for row in active
            ),
            key=lambda item: item["path"],
        )
        imported_department_ids = set()
        for user in users:
            for pk in memberships.get(user["id"], set()):
                row = index.by_id.get(pk)
                if row:
                    imported_department_ids.update(ancestors(row["open_department_id"], index.parent_of))
        people = []
        for user in users:
            department_ids = memberships.get(user["id"], set())
            scoped = user["user_id"] in explicit_users or any(
                index.by_id.get(pk, {}).get("open_department_id") in covered for pk in department_ids
            )
            effective = roles_for(index, user, department_ids, personal.get(user["id"], set()))
            people.append(
                {
                    "id": user["id"],
                    "name": user["name"],
                    "departments": sorted(index.path(item) for item in department_ids),
                    "active": bool(user["active"] and scoped and user["enabled"] and effective),
                    "enabled": user["enabled"],
                    "directoryActive": bool(user["active"] and scoped),
                    "inactiveReason": ("已不在同步范围内" if not scoped else user["inactive_reason"])
                    or ("尚未启用" if not user["enabled"] else "尚未分配角色" if not effective else None),
                    "customRoles": user["custom_roles"],
                    "personalRoles": ordered(personal.get(user["id"], set())),
                    "roles": effective,
                    "lastLoginAt": utc_text(user["last_login_at"]),
                }
            )
        return AccessOverview(
            feishuConfigured=self.feishu.configured,
            roles=[{"code": code, "label": label} for code, label in ROLES.items()],
            departments=departments,
            importedDepartments=[
                item for item in departments if item["openDepartmentId"] in imported_department_ids
            ],
            users=people,
            lastSync=sync_run(last_run),
        )

    def last_sync(self):
        try:
            with self.engine.connect() as connection:
                return sync_run(sync_run_dao.latest(connection))
        except SQLAlchemyError:
            raise ApiError(503, "同步记录读取失败，请检查业务数据库") from None

    def list_users(self, actor, query, department_id, page):
        overview = self.overview(actor)
        users = overview.users
        if department_id is not None:
            with self.engine.connect() as connection:
                index = load_index(connection)
                root = index.by_id.get(department_id)
                covered = subtree([root["open_department_id"]], index.parent_of) if root else set()
                ids = {d["id"] for d in index.by_id.values() if d["open_department_id"] in covered}
                memberships = user_dao.departments_by_user(connection)
            users = [u for u in users if ids.intersection(memberships.get(u.id, set()))]
        users = [u for u in users if query.strip().casefold() in u.name.casefold()]
        return {
            "items": users[(page - 1) * 50 : page * 50],
            "total": len(users),
            "page": page,
            "pageSize": 50,
            "pageCount": max(1, (len(users) + 49) // 50),
        }

    def set_scopes(self, department_ids, actor):
        self.identity.require_manage(actor)
        wanted = set(department_ids)

        def apply(connection, now):
            known = {row["id"] for row in department_dao.all_departments(connection) if row["active"]}
            missing = wanted - known
            if missing:
                raise ApiError(400, "所选部门不存在或已不在飞书通讯录范围内，请先同步飞书部门")
            before = sorted(department_dao.scope_ids(connection))
            department_dao.replace_scopes(connection, wanted, actor, now)
            audit_dao.add(connection, actor, "scope", None, {"before": before, "after": sorted(wanted)}, now)

        self._write(apply, actor)

    def set_department_roles(self, department_id, roles, actor):
        self.identity.require_manage(actor)
        roles = _check_roles(roles)

        def apply(connection, now):
            if department_id not in {row["id"] for row in department_dao.all_departments(connection)}:
                raise ApiError(404, "部门不存在，请先同步飞书部门")
            before = ordered(department_dao.roles_by_department(connection).get(department_id, set()))
            department_dao.replace_roles(connection, department_id, roles, actor, now)
            audit_dao.add(
                connection,
                actor,
                "department_roles",
                str(department_id),
                {"before": before, "after": roles},
                now,
            )

        self._write(apply, actor)

    def set_user_roles(self, user_pk, roles, custom, actor):
        self.identity.require_manage(actor)
        roles = _check_roles(roles)

        def apply(connection, now):
            user = user_dao.get(connection, user_pk, lock=True)
            if user is None:
                raise ApiError(404, "人员不存在，请先同步飞书成员")
            before = {
                "roles": ordered(user_dao.roles_by_user(connection, [user_pk]).get(user_pk, set())),
                "custom": user["custom_roles"],
            }
            user_dao.replace_roles(connection, user_pk, roles, custom, actor, now)
            audit_dao.add(
                connection,
                actor,
                "user_roles",
                str(user_pk),
                {"before": before, "after": {"roles": roles, "custom": custom}},
                now,
            )

        self._write(apply, actor)

    def _write(self, apply, actor):
        try:
            with transaction(self.engine, "identity") as connection:
                self.identity.require_manage(actor)
                apply(connection, _now())
        except IntegrityError:
            raise ApiError(409, "权限正在被同时修改，请刷新后重试") from None
        except SQLAlchemyError:
            raise ApiError(503, "权限保存失败，请检查业务数据库") from None

    def set_user_access(self, user_pk, roles, custom, enabled, actor):
        self.identity.require_manage(actor)
        roles = _check_roles(roles)

        def apply(connection, now):
            user = user_dao.get(connection, user_pk, lock=True)
            if user is None:
                raise ApiError(404, "人员不存在，请先同步飞书成员")
            departments = user_dao.departments_by_user(connection, [user_pk]).get(user_pk, set())
            effective = roles_for(
                load_index(connection), {**user, "custom_roles": custom}, departments, set(roles)
            )
            if enabled and (
                not user["active"]
                or not effective
                or not in_scope(connection, load_index(connection), user, departments)
            ):
                raise ApiError(400, "启用前须确认人员在同步范围内、在职且至少有一个生效角色")
            if user["user_id"] == feishu_user_id(actor) and (not enabled or "admin" not in effective):
                raise ApiError(400, "不能停用当前管理员或移除自身管理员角色，请由其他管理员操作")
            before = {
                "enabled": user["enabled"],
                "customRoles": user["custom_roles"],
                "roles": ordered(user_dao.roles_by_user(connection, [user_pk]).get(user_pk, set())),
            }
            user_dao.replace_roles(connection, user_pk, roles, custom, actor, now)
            user_dao.set_enabled(connection, user_pk, enabled, now)
            audit_dao.add(
                connection,
                actor,
                "user_access",
                str(user_pk),
                {"before": before, "after": {"enabled": enabled, "customRoles": custom, "roles": roles}},
                now,
            )

        self._write(apply, actor)
