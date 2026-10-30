"""真实服务链路使用隔离数据库和飞书传输替身，验证选择、授权及失败保护。"""

from datetime import timedelta

import pytest
from alembic import command
from backend.app import create_app
from backend.core.database import make_engine
from backend.manage import SCHEMA_INI, _config, upgrade_schema
from backend.modules.identity.dao import directory_preview_dao, user_dao
from backend.modules.identity.service.directory_preview_service import now
from backend.modules.identity.service.directory_sync_service import DirectorySyncService
from backend.tests.identity.test_feishu_login import (
    FINANCE,
    OTHER,
    PURCHASE,
    PURCHASE_A,
    FakeFeishu,
    admin_client,
    application_clients,
    feishu_login,
)
from sqlalchemy import text


@pytest.fixture
def system(context):
    feishu = FakeFeishu()
    app = create_app(context.settings, context.ns, context.engine, feishu=feishu)
    with application_clients(app, context.settings):
        client = admin_client(app, context.settings)
        yield app, client, feishu, {"Origin": context.settings.origin}


def preview(client, headers):
    response = client.post("/api/identity/directory/previews", json={}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def submit(client, headers, pid, departments=(), users=()):
    return client.post(
        f"/api/identity/directory/previews/{pid}/sync",
        json={"departmentIds": list(departments), "userIds": list(users)},
        headers=headers,
    )


def enable(client, headers, user, roles=("purchaser",), enabled=True):
    return client.put(
        f"/api/identity/users/{user['id']}/access",
        json={"roles": list(roles), "customRoles": True, "enabled": enabled},
        headers=headers,
    )


def test_preview_import_one_and_enable_then_disable_session(system, context):
    app, client, feishu, headers = system
    pid = preview(client, headers)
    assert client.get("/api/identity/access").json()["users"] == []
    response = submit(client, headers, pid, users=["u-zhang"])
    assert response.status_code == 200, response.text
    user = client.get("/api/identity/access").json()["users"][0]
    assert user["name"] == "张采购" and not user["enabled"] and not user["active"]
    denied, _, _ = feishu_login(app, context.settings, feishu, "u-zhang")
    assert denied.get("/api/session").status_code == 401
    assert enable(client, headers, user, roles=[]).status_code == 400
    assert enable(client, headers, user).status_code == 200
    signed, _, _ = feishu_login(app, context.settings, feishu, "u-zhang")
    assert signed.get("/api/session").status_code == 200
    assert enable(client, headers, user, enabled=False).status_code == 200
    assert signed.get("/api/session").status_code == 401
    # 定时同步不重新启用被手动停用的成员。
    DirectorySyncService(context.engine, feishu).sync("schedule", "system")
    assert not client.get("/api/identity/access").json()["users"][0]["enabled"]


def test_imported_department_navigation_hides_empty_but_keeps_ancestors_and_disabled_users(system):
    _, client, _, headers = system
    assert client.get("/api/identity/access").json()["importedDepartments"] == []
    pid = preview(client, headers)
    assert submit(client, headers, pid, users=["u-li"]).status_code == 200
    overview = client.get("/api/identity/access").json()
    # 未启用员工也是已导入员工；上级虽无直属员工，仍可展开查看下级。
    assert not overview["users"][0]["enabled"]
    assert {d["name"] for d in overview["importedDepartments"]} == {"上海毅鑫", "采购部", "采购一组"}
    assert {d["name"] for d in overview["departments"]} == {
        "上海毅鑫",
        "采购部",
        "采购一组",
        "财务部",
        "行政部",
    }
    for department in overview["importedDepartments"]:
        assert client.get(f"/api/identity/users?department_id={department['id']}").json()["total"] == 1
    # 隐藏只影响本地导航，不删除部门，也不缩减再次读取飞书的选择范围。
    response = client.post("/api/identity/directory/previews", json={}, headers=headers)
    assert {d["name"] for d in response.json()["departments"]} == {d["name"] for d in overview["departments"]}


def test_whole_subtree_union_and_future_members(system, context):
    _, client, feishu, headers = system
    pid = preview(client, headers)
    response = submit(client, headers, pid, departments=[PURCHASE], users=["u-zhang", "u-wang"])
    assert response.status_code == 200
    assert response.json()["run"]["usersAdded"] == 3
    feishu.members[PURCHASE_A].append(feishu.person("u-new", "新增采购"))
    feishu.members[FINANCE].append(feishu.person("u-extra", "不应导入"))
    service = DirectorySyncService(context.engine, feishu)
    assert service.due(timedelta(seconds=0))
    service.sync("schedule", "system")
    users = client.get("/api/identity/access").json()["users"]
    assert {u["name"] for u in users} == {"张采购", "李采购", "王财务", "新增采购"}
    assert not any(u["enabled"] for u in users)


def test_individual_follows_department_move_and_failure_is_atomic(system, context):
    _, client, feishu, headers = system
    submit(client, headers, preview(client, headers), users=["u-zhang"])
    user = client.get("/api/identity/access").json()["users"][0]
    enable(client, headers, user)
    feishu.members[OTHER].extend(feishu.members.pop(PURCHASE))
    service = DirectorySyncService(context.engine, feishu)
    assert service.due(timedelta(seconds=0))
    service.sync("schedule", "system")
    user = client.get("/api/identity/access").json()["users"][0]
    assert any("行政部" in d for d in user["departments"]) and user["active"]
    feishu.fail_users = True
    assert client.post("/api/identity/directory/previews", json={}, headers=headers).status_code == 502
    assert client.get("/api/identity/access").json()["users"][0]["active"]


def test_tamper_stale_replay_and_removal_preview(system, context):
    _, client, _, headers = system
    pid = preview(client, headers)
    assert submit(client, headers, pid, users=["forged"]).status_code == 400
    first = submit(client, headers, pid, users=["u-zhang"])
    assert submit(client, headers, pid, users=["u-zhang"]).json() == first.json()
    assert submit(client, headers, pid, users=["u-wang"]).status_code == 409
    pid = preview(client, headers)
    user = client.get("/api/identity/access").json()["users"][0]
    enable(client, headers, user)
    assert submit(client, headers, pid, users=["u-wang"]).status_code == 409
    pid = preview(client, headers)
    plan = client.post(
        f"/api/identity/directory/previews/{pid}/plan",
        json={"departmentIds": [], "userIds": []},
        headers=headers,
    )
    assert plan.json()["removedNames"] == ["张采购"]
    assert submit(client, headers, pid).status_code == 200
    assert not client.get("/api/identity/access").json()["users"][0]["active"]


def test_missing_fields_expiry_and_nonadmin(system, context):
    app, client, feishu, headers = system
    pid = preview(client, headers)
    with context.engine.begin() as connection:
        row = directory_preview_dao.get(connection, pid)
        # 用 DAO 写入过期快照，不修改真实业务表或环境。
        directory_preview_dao.create(
            connection,
            {
                "id": "expired",
                "actor": row["actor"],
                "version": row["version"],
                "payload": row["payload"],
                "expires_at": now() - timedelta(seconds=1),
            },
            now(),
        )
    assert submit(client, headers, "expired").status_code == 409
    submit(client, headers, pid, users=["u-zhang"])
    user = client.get("/api/identity/access").json()["users"][0]
    enable(client, headers, user)
    signed, _, _ = feishu_login(app, context.settings, feishu, "u-zhang")
    assert signed.post("/api/identity/directory/previews", json={}, headers=headers).status_code == 403
    assert (
        signed.post(
            f"/api/identity/directory/previews/{pid}/members",
            json={"departmentId": PURCHASE},
            headers=headers,
        ).status_code
        == 403
    )
    feishu.departments[PURCHASE].pop("name")
    assert client.post("/api/identity/directory/previews", json={}, headers=headers).status_code == 502
    with context.engine.connect() as connection:
        assert user_dao.all_users(connection)[0]["enabled"]


def test_direct_children_reconstruct_tree_without_parent_field(system, monkeypatch):
    _, client, feishu, headers = system
    original = feishu.department
    monkeypatch.setattr(
        feishu,
        "department",
        lambda key: {k: v for k, v in original(key).items() if k != "parent_department_id"},
    )
    result = client.post("/api/identity/directory/previews", json={}, headers=headers)
    assert result.status_code == 200
    child = next(d for d in result.json()["departments"] if d["id"] == PURCHASE_A)
    assert child["path"].endswith("采购部 / 采购一组") and child["depth"] == 2
    assert (
        submit(client, headers, result.json()["id"], departments=[PURCHASE]).json()["run"]["usersAdded"] == 2
    )


def test_member_filter_pagination_and_union(system):
    _, client, feishu, headers = system
    feishu.members[FINANCE].append(feishu.members[PURCHASE][0])
    feishu.members[PURCHASE].extend(feishu.person(f"many-{i}", f"测试{i:03}") for i in range(55))
    pid = preview(client, headers)
    body = {"departmentId": PURCHASE, "departmentIds": [FINANCE], "userIds": ["u-zhang"], "page": 1}
    result = client.post(f"/api/identity/directory/previews/{pid}/members", json=body, headers=headers).json()
    assert result["total"] == 56 and len(result["items"]) == 50
    result = client.post(
        f"/api/identity/directory/previews/{pid}/members", json={**body, "query": "张采购"}, headers=headers
    ).json()
    assert result["total"] == 1 and result["selectedCount"] == 3
    assert result["items"][0]["coveredByDepartment"]


def test_scope_removed_revokes_session_before_legacy_sync(system, context):
    app, client, feishu, headers = system
    submit(client, headers, preview(client, headers), departments=[PURCHASE])
    user = next(u for u in client.get("/api/identity/access").json()["users"] if u["name"] == "张采购")
    enable(client, headers, user)
    signed, _, _ = feishu_login(app, context.settings, feishu, "u-zhang")
    assert signed.get("/api/session").status_code == 200
    client.put("/api/identity/scopes", json={"departmentIds": []}, headers=headers)
    assert signed.get("/api/session").status_code == 401
    assert enable(client, headers, user).status_code == 400


def test_scheduled_read_cannot_overwrite_changed_permissions(system, context, monkeypatch):
    _, client, feishu, headers = system
    submit(client, headers, preview(client, headers), users=["u-zhang"])
    user = client.get("/api/identity/access").json()["users"][0]
    original = feishu.department_users
    changed = False

    def read(department):
        nonlocal changed
        if not changed:
            changed = True
            assert enable(client, headers, user).status_code == 200
        return original(department)

    monkeypatch.setattr(feishu, "department_users", read)
    response = client.post("/api/identity/sync", json={}, headers=headers)
    assert response.status_code == 502
    assert client.get("/api/identity/access").json()["users"][0]["active"]


def test_upgrade_preserves_existing_accounts_but_new_users_require_enable(tmp_path):
    url = f"sqlite:///{tmp_path / 'before-enable.sqlite'}"
    command.upgrade(_config(SCHEMA_INI, url), "0034_source_customs_declared_unit_price")
    engine = make_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO identity_users (user_id, name, synced_at, active) VALUES ('old', '原有停用人员', '2026-10-28', 0)"
                )
            )
        upgrade_schema(url)
        with engine.begin() as connection:
            old = user_dao.by_user_id(connection, "old")
            assert old["enabled"] and not old["active"]
            connection.execute(
                text(
                    "INSERT INTO identity_users (user_id, name, synced_at) VALUES ('new', '新成员', '2026-10-28')"
                )
            )
            assert not user_dao.by_user_id(connection, "new")["enabled"]
    finally:
        engine.dispose()
