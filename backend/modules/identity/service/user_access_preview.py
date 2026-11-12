"""在同一数据库快照中计算成员草稿权限及保存版本，不在前端推算继承。"""

import hashlib
import json

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import role_page_dao, user_dao
from ..policy.page_policy import effective_pages, page_items
from ..policy.role_policy import effective_roles, ordered, unknown_roles
from ..vo.role_page_vo import UserAccessDetail, UserAccessPreview
from .access_reader import in_scope, load_index


def evaluate(connection, user, roles, custom):
    if unknown_roles(roles):
        raise ApiError(400, "包含未知角色，请重新选择")
    departments = user_dao.departments_by_user(connection, [user["id"]]).get(user["id"], set())
    personal = user_dao.roles_by_user(connection, [user["id"]]).get(user["id"], set())
    index = load_index(connection)
    inherited = ordered(index.inherited_roles(departments))
    effective = effective_roles(inherited, roles, custom)
    scoped = in_scope(connection, index, user, departments)
    configurations = role_page_dao.configurations(connection)
    state = {
        "user": {key: user[key] for key in ("id", "enabled", "active", "custom_roles")},
        "personal": ordered(personal),
        "inherited": inherited,
        "scope": scoped,
        "pages": {
            code: {"pages": row["pages"], "revision": row["revision"]} for code, row in configurations.items()
        },
    }
    version = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    reason = None
    if not user["active"] or not scoped:
        reason = user["inactive_reason"] or "人员不在同步范围内或不在职"
    elif not effective:
        reason = "启用前至少需要一个生效角色"
    return UserAccessPreview(
        version=version,
        inheritedRoles=inherited,
        roles=effective,
        pages=page_items(effective_pages(effective, configurations)),
        canEnable=reason is None,
        reason=reason,
    )


class UserAccessPreviewService:
    def __init__(self, engine, identity):
        self.engine, self.identity = engine, identity

    def preview(self, user_pk, roles, custom, actor):
        self.identity.require_manage(actor)
        try:
            with self.engine.connect() as connection:
                user = user_dao.get(connection, user_pk)
                if user is None:
                    raise ApiError(404, "人员不存在，请刷新列表")
                return evaluate(connection, user, roles, custom)
        except SQLAlchemyError:
            raise ApiError(503, "成员权限预览失败，请检查业务数据库") from None

    def detail(self, user_pk, actor):
        self.identity.require_manage(actor)
        try:
            with self.engine.connect() as connection:
                user = user_dao.get(connection, user_pk)
                if user is None:
                    raise ApiError(404, "人员不存在，请刷新列表")
                personal = ordered(user_dao.roles_by_user(connection, [user_pk]).get(user_pk, set()))
                departments = user_dao.departments_by_user(connection, [user_pk]).get(user_pk, set())
                index = load_index(connection)
                return UserAccessDetail(
                    id=user_pk,
                    name=user["name"],
                    departments=sorted(index.path(pk) for pk in departments),
                    personalRoles=personal,
                    customRoles=user["custom_roles"],
                    enabled=user["enabled"],
                    preview=evaluate(connection, user, personal, user["custom_roles"]),
                )
        except SQLAlchemyError:
            raise ApiError(503, "成员权限读取失败，请检查业务数据库") from None
