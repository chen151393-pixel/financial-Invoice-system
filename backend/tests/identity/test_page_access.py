"""用真实身份链路验证页面授权、成员草稿与直接 API 访问；不调用真实飞书或 NS。"""

import pytest
from alembic import command
from backend.app import create_app
from backend.core.dependencies import current_owner
from backend.manage import SCHEMA_INI, _config
from backend.modules.identity.dao import role_page_dao
from backend.modules.identity.entity import audit
from backend.modules.identity.policy.api_page_policy import required_pages
from backend.modules.identity.policy.page_policy import PAGE_CODES
from backend.tests.identity.test_feishu_login import (
    FakeFeishu,
    admin_client,
    application_clients,
    feishu_login,
    setup_directory,
)
from fastapi.routing import APIRoute
from sqlalchemy import select


@pytest.fixture
def system(context):
    feishu = FakeFeishu()
    app = create_app(context.settings, context.ns, context.engine, feishu=feishu)
    with application_clients(app, context.settings):
        admin = admin_client(app, context.settings)
        setup_directory(admin, context.settings)
        yield app, admin, feishu, {"Origin": context.settings.origin}


def grant(admin, headers, role, pages, revision=0):
    return admin.put(
        f"/api/identity/role-pages/{role}", json={"pages": pages, "revision": revision}, headers=headers
    )


def member(admin, name="王财务"):
    return next(row for row in admin.get("/api/identity/access").json()["users"] if row["name"] == name)


def test_role_configuration_versions_audit_and_persistence(system, context):
    _, admin, _, headers = system
    overview = admin.get("/api/identity/role-pages").json()
    assert len(overview["pages"]) == 10
    assert all(page["assignable"] for page in overview["pages"])
    assert overview["roles"][0]["editable"] is False
    saved = grant(admin, headers, "finance", ["finance", "finance"])
    assert saved.status_code == 200
    assert saved.json()["pages"] == ["finance"] and saved.json()["revision"] == 1
    assert grant(admin, headers, "finance", ["invoices"]).status_code == 409
    assert grant(admin, headers, "finance", [], 1).json()["pages"] == []
    with context.engine.connect() as connection:
        assert role_page_dao.configurations(connection)["finance"]["pages"] == []
        changes = connection.execute(select(audit).where(audit.c.action == "role_pages")).mappings().all()
        assert len(changes) == 2
        assert changes[-1]["actor"] == f"user:{context.settings.admin_user}"


@pytest.mark.parametrize(
    "role,pages,status",
    [
        ("root", ["finance"], 404),
        ("admin", [], 400),
        ("finance", ["unknown"], 400),
    ],
)
def test_reject_invalid_or_fixed_role_grants(system, role, pages, status):
    _, admin, _, headers = system
    assert grant(admin, headers, role, pages).status_code == status


def test_live_revoke_session_pages_without_relogin_and_admin_is_fixed(system, context):
    app, admin, feishu, headers = system
    user, _, _ = feishu_login(app, context.settings, feishu, "u-wang")
    assert "finance" in user.get("/api/session").json()["user"]["pages"]
    grant(admin, headers, "finance", ["invoices"])
    assert user.get("/api/session").json()["user"]["pages"] == ["invoices"]
    assert user.post("/api/review/declarations/query", json={}, headers=headers).status_code == 403
    assert user.get("/api/invoices/stats").status_code == 200
    assert user.get("/api/matching/invoice-totals").status_code == 200
    assert user.post("/api/matching/invoices/query", json={}, headers=headers).status_code == 200
    assert user.post("/api/matching/orders/confirm", json={}, headers=headers).status_code == 403
    assert user.get("/api/identity/role-pages").status_code == 403
    assert grant(user, headers, "finance", ["access"], 1).status_code == 403
    grant(admin, headers, "finance", [], 1)
    assert user.get("/api/session").json()["user"]["pages"] == []
    assert admin.get("/api/session").json()["user"]["pages"] == list(PAGE_CODES)
    assert not context.ns.writes


def test_admin_can_delegate_access_page_and_delegated_member_can_manage(system, context):
    app, admin, feishu, headers = system
    saved = grant(admin, headers, "finance_manager", ["finance", "access"])
    assert saved.status_code == 200
    assert saved.json()["pages"] == ["finance", "access"]
    person = member(admin)
    endpoint = f"/api/identity/users/{person['id']}/access"
    assert (
        admin.put(
            endpoint,
            json={"roles": ["finance_manager"], "customRoles": True, "enabled": True},
            headers=headers,
        ).status_code
        == 200
    )
    manager, _, _ = feishu_login(app, context.settings, feishu, "u-wang")
    session = manager.get("/api/session").json()["user"]
    assert session["roles"] == [{"code": "finance_manager", "label": "财务主管"}]
    assert session["canManageAccess"] and session["pages"] == ["finance", "access"]
    assert manager.get("/api/identity/access").status_code == 200
    assert manager.get("/api/identity/users").status_code == 200
    assert manager.get("/api/identity/role-pages").status_code == 200
    # 能将同一页面继续授予其他角色，不能只做到菜单可见。
    assert grant(manager, headers, "viewer", ["pl", "access"]).status_code == 200
    detail = manager.get(endpoint).json()
    assert (
        manager.put(
            endpoint,
            json={
                "roles": ["finance_manager"],
                "customRoles": True,
                "enabled": True,
                "version": detail["preview"]["version"],
            },
            headers=headers,
        ).status_code
        == 200
    )
    other = member(admin, "张采购")
    assert (
        manager.put(
            f"/api/identity/users/{other['id']}/access",
            json={"roles": [], "customRoles": False, "enabled": False},
            headers=headers,
        ).status_code
        == 200
    )
    assert manager.post("/api/identity/directory/previews", json={}, headers=headers).status_code == 200
    assert grant(admin, headers, "finance_manager", ["finance"], 1).status_code == 200
    assert not manager.get("/api/session").json()["user"]["canManageAccess"]
    assert manager.get("/api/identity/access").status_code == 403
    assert grant(manager, headers, "finance", ["access"]).status_code == 403
    assert not context.ns.writes


def test_purchase_manager_available_configurable_and_assignable_to_members_and_departments(system, context):
    app, admin, feishu, headers = system
    overview = admin.get("/api/identity/role-pages").json()
    roles = overview["roles"]
    codes = [role["code"] for role in roles]
    role = next(role for role in roles if role["code"] == "purchase_manager")
    assert role["label"] == "采购主管" and role["editable"]
    assert codes.index("purchase_manager") < codes.index("purchaser")
    directory = admin.get("/api/identity/access").json()
    assert {"code": "purchase_manager", "label": "采购主管"} in directory["roles"]
    pages = ["workbench", "invoice-followup", "supplier-profiles", "pl", "writeback", "access"]
    configured = grant(admin, headers, "purchase_manager", pages)
    assert configured.status_code == 200 and configured.json()["pages"] == pages
    department = next(item for item in directory["departments"] if item["name"] == "采购部")
    assert (
        admin.put(
            f"/api/identity/departments/{department['id']}/roles",
            json={"roles": ["purchase_manager"]},
            headers=headers,
        ).status_code
        == 200
    )
    assert member(admin, "李采购")["roles"] == ["purchase_manager"]
    inherited, _, _ = feishu_login(app, context.settings, feishu, "u-li")
    session = inherited.get("/api/session").json()["user"]
    assert session["roles"] == [{"code": "purchase_manager", "label": "采购主管"}]
    assert session["pages"] == pages and session["canManageAccess"]
    person = member(admin)
    endpoint = f"/api/identity/users/{person['id']}/access"
    version = admin.get(endpoint).json()["preview"]["version"]
    assert (
        admin.put(
            endpoint,
            json={"roles": ["purchase_manager"], "customRoles": True, "enabled": True, "version": version},
            headers=headers,
        ).status_code
        == 200
    )
    personal, _, _ = feishu_login(app, context.settings, feishu, "u-wang")
    assert personal.get("/api/session").json()["user"]["roles"] == session["roles"]
    assert personal.get("/api/session").json()["user"]["pages"] == pages
    assert not context.ns.writes


def test_preview_inheritance_union_override_and_no_write(system, context):
    app, admin, feishu, headers = system
    grant(admin, headers, "finance", ["finance"])
    grant(admin, headers, "purchaser", ["invoice-followup", "writeback"])
    row = member(admin)
    url = f"/api/identity/users/{row['id']}"
    detail = admin.get(url + "/access").json()
    response = admin.post(
        url + "/access-preview", json={"roles": ["purchaser"], "customRoles": False}, headers=headers
    )
    assert response.status_code == 200
    preview = response.json()
    assert preview["inheritedRoles"] == ["finance"]
    assert preview["roles"] == ["finance", "purchaser"]
    assert {page["code"] for page in preview["pages"]} == {"finance", "invoice-followup", "writeback"}
    assert member(admin)["roles"] == ["finance"]
    body = {
        "roles": ["purchaser"],
        "customRoles": True,
        "enabled": True,
        "version": detail["preview"]["version"],
    }
    assert admin.put(url + "/access", json=body, headers=headers).status_code == 200
    user, _, _ = feishu_login(app, context.settings, feishu, "u-wang")
    assert user.get("/api/session").json()["user"]["pages"] == ["invoice-followup", "writeback"]
    # 旧页面不能覆盖后来保存的个人角色。
    assert admin.put(url + "/access", json={**body, "roles": ["finance"]}, headers=headers).status_code == 409


def test_role_change_invalidates_member_preview_and_disable_invalidates_session(system, context):
    app, admin, feishu, headers = system
    row = member(admin)
    url = f"/api/identity/users/{row['id']}/access"
    version = admin.get(url).json()["preview"]["version"]
    grant(admin, headers, "finance", ["finance"])
    body = {"roles": [], "customRoles": False, "enabled": True, "version": version}
    assert admin.put(url, json=body, headers=headers).status_code == 409
    user, _, _ = feishu_login(app, context.settings, feishu, "u-wang")
    body.update(version=admin.get(url).json()["preview"]["version"], enabled=False)
    assert admin.put(url, json=body, headers=headers).status_code == 200
    assert user.get("/api/session").status_code == 401


def test_preview_cannot_forge_person_or_effective_permissions(system):
    _, admin, _, headers = system
    url = f"/api/identity/users/{member(admin)['id']}/access-preview"
    for body in (
        {"roles": ["root"], "customRoles": True},
        {"roles": [], "customRoles": True, "pages": ["access"]},
    ):
        assert admin.post(url, json=body, headers=headers).status_code == 400
    empty = admin.post(url, json={"roles": [], "customRoles": True}, headers=headers).json()
    assert empty["canEnable"] is False and empty["roles"] == [] and empty["pages"] == []


def test_all_protected_routes_have_mapping_and_no_page_cannot_call_them(system, context):
    app, admin, feishu, headers = system
    grant(admin, headers, "finance", [])
    user, _, _ = feishu_login(app, context.settings, feishu, "u-wang")
    checked = 0

    def routes(router):
        for route in router.routes:
            if isinstance(route, APIRoute):
                yield route
            elif hasattr(route, "original_router"):
                yield from routes(route.original_router)

    for route in routes(app.router):
        if not isinstance(route, APIRoute) or not any(
            d.call is current_owner for d in route.dependant.dependencies
        ):
            continue
        for method in route.methods:
            required = required_pages(method, route.path)
            assert required is None or required, f"未登记页面权限：{method} {route.path}"
            if required is None:
                continue
            path = route.path
            for param in route.param_convertors:
                path = path.replace("{" + param + "}", "1")
            response = user.request(
                method, path, **({"json": {}} if method not in {"GET", "HEAD"} else {}), headers=headers
            )
            assert response.status_code == 403, (method, path, response.text)
            checked += 1
    assert checked > 100
    assert not context.ns.writes


def test_configured_permissions_cannot_be_downgraded_away(system, context):
    _, admin, _, headers = system
    assert grant(admin, headers, "finance", ["finance"]).status_code == 200
    with pytest.raises(RuntimeError, match="不能降级删除"):
        command.downgrade(
            _config(SCHEMA_INI, context.engine.url.render_as_string(hide_password=False)),
            "0040_sync_ns_plans",
        )
