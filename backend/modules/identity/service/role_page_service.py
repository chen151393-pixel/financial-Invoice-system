"""角色页面配置：identity 模块锁、乐观版本与审计。"""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import audit_dao, role_page_dao
from ..policy.page_policy import PAGE_CODES, default_pages, page_items
from ..policy.role_policy import ROLES
from ..vo.role_page_vo import RolePageOverview, RolePages


def role_item(code, row):
    return RolePages(
        code=code,
        label=ROLES[code],
        pages=default_pages(code) if row is None or code == "admin" else row["pages"],
        revision=row["revision"] if row else 0,
        editable=code != "admin",
    )


class RolePageService:
    def __init__(self, engine, identity):
        self.engine, self.identity = engine, identity

    def overview(self, actor):
        self.identity.require_manage(actor)
        try:
            with self.engine.connect() as connection:
                rows = role_page_dao.configurations(connection)
        except SQLAlchemyError:
            raise ApiError(503, "角色页面权限读取失败，请检查业务数据库") from None
        return RolePageOverview(pages=page_items(), roles=[role_item(code, rows.get(code)) for code in ROLES])

    def save(self, role, pages, revision, actor):
        self.identity.require_manage(actor)
        if role not in ROLES:
            raise ApiError(404, "角色不存在")
        if role == "admin":
            raise ApiError(400, "系统管理员固定拥有全部页面权限，不能修改")
        if set(pages) - set(PAGE_CODES):
            raise ApiError(400, "包含未知页面，请刷新后重新选择")
        pages = [code for code in PAGE_CODES if code in pages]
        try:
            with transaction(self.engine, "identity") as connection:
                self.identity.require_manage(actor)
                before = role_item(role, role_page_dao.configurations(connection).get(role))
                if revision != before.revision:
                    raise ApiError(409, "角色页面权限已被修改，请重新读取后再保存")
                now = datetime.now(UTC).replace(tzinfo=None)
                role_page_dao.save(connection, role, pages, revision, actor, now)
                audit_dao.add(
                    connection,
                    actor,
                    "role_pages",
                    role,
                    {"before": before.model_dump(), "after": {"pages": pages, "revision": revision + 1}},
                    now,
                )
        except IntegrityError:
            raise ApiError(409, "角色页面权限正在被修改，请重新读取后再保存") from None
        except SQLAlchemyError:
            raise ApiError(503, "角色页面权限保存失败，请检查业务数据库") from None
        return role_item(role, {"pages": pages, "revision": revision + 1})
