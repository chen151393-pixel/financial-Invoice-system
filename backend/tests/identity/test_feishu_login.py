"""飞书登录、部门与成员同步、权限管理：使用模拟飞书接口，不访问真实飞书。"""

from urllib.parse import parse_qs, urlsplit

import pytest
from backend.app import create_app
from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.modules.identity.policy.department_policy import ancestors, subtree
from backend.modules.identity.policy.login_policy import inactive_reason, safe_return_path
from fastapi.testclient import TestClient

ROOT, PURCHASE, PURCHASE_A, FINANCE, OTHER = (
    "od-root",
    "od-purchase",
    "od-purchase-a",
    "od-finance",
    "od-other",
)


class FakeFeishu:
    """按飞书开放平台返回结构模拟；department_users 只返回直属成员。"""

    configured = True

    def __init__(self):
        self.departments = {
            ROOT: {"name": "上海毅鑫", "parent_department_id": "0"},
            PURCHASE: {"name": "采购部", "parent_department_id": ROOT},
            PURCHASE_A: {"name": "采购一组", "parent_department_id": PURCHASE},
            FINANCE: {"name": "财务部", "parent_department_id": ROOT},
            OTHER: {"name": "行政部", "parent_department_id": ROOT},
        }
        self.members = {
            PURCHASE: [self.person("u-zhang", "张采购")],
            PURCHASE_A: [self.person("u-li", "李采购")],
            FINANCE: [self.person("u-wang", "王财务"), self.person("u-quit", "赵离职", is_resigned=True)],
            OTHER: [self.person("u-zhou", "周行政")],
        }
        self.codes = {}
        self.tenant = "tenant-ok"
        self.fail_users = False
        self.states = []

    @staticmethod
    def person(user_id, name, **status):
        return {
            "user_id": user_id,
            "open_id": f"ou-{user_id}",
            "union_id": f"on-{user_id}",
            "name": name,
            "avatar": {"avatar_72": "https://example.invalid/a.png"},
            "status": {"is_activated": True, **status},
        }

    def authorize_url(self, state):
        self.states.append(state)
        return f"https://accounts.feishu.cn/open-apis/authen/v1/authorize?state={state}"

    def exchange_code(self, code):
        if code not in self.codes:
            raise ApiError(502, "飞书接口调用失败（20003）：飞书授权码无效，请重新登录")
        return f"token-{code}"

    def user_info(self, token):
        user_id = self.codes[token.removeprefix("token-")]
        return {"user_id": user_id, "name": user_id, "tenant_key": self.tenant}

    def scope_department_ids(self):
        return [ROOT]

    def department(self, open_id):
        return {"open_department_id": open_id, **self.departments[open_id]}

    def child_departments(self, open_id):
        found = [
            key
            for key, value in self.departments.items()
            if key in subtree([open_id], self.parents()) and key != open_id
        ]
        return [self.department(key) for key in found]

    def parents(self):
        return {key: value["parent_department_id"] for key, value in self.departments.items()}

    def department_users(self, open_id):
        if self.fail_users:
            raise ApiError(502, "飞书接口调用失败（99991672）：飞书应用缺少通讯录权限")
        return self.members.get(open_id, [])


@pytest.fixture
def feishu():
    return FakeFeishu()


@pytest.fixture
def app(context, feishu):
    return create_app(context.settings, context.ns, context.engine, feishu=feishu)


def admin_client(app, settings):
    client = TestClient(app, base_url=settings.origin)
    client.__enter__()
    headers = {"Origin": settings.origin}
    body = {"username": settings.admin_user, "password": settings.admin_password}
    assert client.post("/api/session", json=body, headers=headers).status_code == 200
    return client


def setup_directory(client, settings, *, scopes=("采购部", "财务部"), roles=None):
    headers = {"Origin": settings.origin}
    assert client.post("/api/identity/sync", json={}, headers=headers).status_code == 200
    departments = {
        item["name"]: item["id"] for item in client.get("/api/identity/access").json()["departments"]
    }
    ids = [departments[name] for name in scopes]
    assert client.put("/api/identity/scopes", json={"departmentIds": ids}, headers=headers).status_code == 200
    for name, codes in (roles or {"采购部": ["purchaser"], "财务部": ["finance"]}).items():
        response = client.put(
            f"/api/identity/departments/{departments[name]}/roles", json={"roles": codes}, headers=headers
        )
        assert response.status_code == 200
    # 设置范围后再同步一次，才会拉取范围内成员
    assert client.post("/api/identity/sync", json={}, headers=headers).status_code == 200
    return departments


def feishu_login(app, settings, feishu, user_id, *, return_to="/review?status=pending"):
    client = TestClient(app, base_url=settings.origin, follow_redirects=False)
    client.__enter__()
    response = client.post(
        "/api/session/feishu/start", json={"returnTo": return_to}, headers={"Origin": settings.origin}
    )
    assert response.status_code == 200
    state = parse_qs(urlsplit(response.json()["url"]).query)["state"][0]
    code = f"code-{user_id}"
    feishu.codes[code] = user_id
    callback = client.get("/api/session/feishu/callback", params={"code": code, "state": state})
    assert callback.status_code == 303
    return client, callback, state


def test_feishu_login_issues_session_with_inherited_roles(app, context, feishu):
    settings = context.settings
    admin = admin_client(app, settings)
    setup_directory(admin, settings)
    users = {item["name"]: item for item in admin.get("/api/identity/access").json()["users"]}
    # 李采购在采购部下级“采购一组”，继承采购部默认角色；离职人员不可登录
    assert users["李采购"]["roles"] == ["purchaser"]
    assert users["赵离职"]["active"] is False and users["赵离职"]["inactiveReason"] == "已离职"
    assert "周行政" not in users

    client, callback, _ = feishu_login(app, settings, feishu, "u-li")
    assert callback.headers["location"] == "/review?status=pending"
    session = client.get("/api/session").json()
    assert session["user"] == {
        "kind": "feishu",
        "name": "李采购",
        "roles": [{"code": "purchaser", "label": "采购专员"}],
        "canManageAccess": False,
    }
    assert app.state.identity.owner(session_token=client.cookies.get("ns_session")) == "user:fs:u-li"
    # 非系统管理员不能打开权限管理
    assert client.get("/api/identity/access").status_code == 403
    assert client.get("/api/session/feishu/outcome").json()["status"] == "success"


@pytest.mark.parametrize(
    "user_id,reason",
    [
        ("u-zhou", "你不在系统使用范围内"),
        ("u-quit", "已离职"),
    ],
)
def test_feishu_login_rejects_people_outside_scope_or_resigned(app, context, feishu, user_id, reason):
    admin = admin_client(app, context.settings)
    setup_directory(admin, context.settings)
    client, callback, _ = feishu_login(app, context.settings, feishu, user_id)
    assert callback.headers["location"] == "/login"
    assert not client.cookies.get("ns_session")
    outcome = client.get("/api/session/feishu/outcome").json()
    assert outcome["status"] == "failed" and reason in outcome["reason"]


def test_feishu_login_requires_a_role(app, context, feishu):
    admin = admin_client(app, context.settings)
    setup_directory(admin, context.settings, roles={"采购部": ["purchaser"]})
    client, callback, _ = feishu_login(app, context.settings, feishu, "u-wang")
    assert callback.headers["location"] == "/login"
    assert "还没有分配角色" in client.get("/api/session/feishu/outcome").json()["reason"]


def test_state_is_single_use_and_bound_to_browser(app, context, feishu):
    admin = admin_client(app, context.settings)
    setup_directory(admin, context.settings)
    client, _, state = feishu_login(app, context.settings, feishu, "u-wang")
    feishu.codes["code-again"] = "u-wang"
    replay = client.get("/api/session/feishu/callback", params={"code": "code-again", "state": state})
    assert replay.headers["location"] == "/login"
    # 另一个浏览器拿到授权码与 state 也不能登录
    other = TestClient(app, base_url=context.settings.origin, follow_redirects=False)
    start = other.post(
        "/api/session/feishu/start", json={"returnTo": "/tasks"}, headers={"Origin": context.settings.origin}
    )
    foreign_state = parse_qs(urlsplit(start.json()["url"]).query)["state"][0]
    stranger = TestClient(app, base_url=context.settings.origin, follow_redirects=False)
    feishu.codes["code-x"] = "u-wang"
    response = stranger.get("/api/session/feishu/callback", params={"code": "code-x", "state": foreign_state})
    assert response.headers["location"] == "/login" and not stranger.cookies.get("ns_session")
    # 原浏览器的流程未被他人作废，仍可完成
    response = other.get("/api/session/feishu/callback", params={"code": "code-x", "state": foreign_state})
    assert response.headers["location"] == "/tasks" and other.cookies.get("ns_session")


def test_cancelled_authorization_and_wrong_tenant(app, context, feishu):
    admin = admin_client(app, context.settings)
    setup_directory(admin, context.settings)
    client = TestClient(app, base_url=context.settings.origin, follow_redirects=False)
    start = client.post("/api/session/feishu/start", json={}, headers={"Origin": context.settings.origin})
    state = parse_qs(urlsplit(start.json()["url"]).query)["state"][0]
    client.get("/api/session/feishu/callback", params={"error": "access_denied", "state": state})
    assert "取消了飞书授权" in client.get("/api/session/feishu/outcome").json()["reason"]

    context.settings.feishu_tenant_key = "tenant-company"
    _, callback, _ = feishu_login(app, context.settings, feishu, "u-wang")
    assert callback.headers["location"] == "/login"


def test_start_rejects_foreign_origin_and_unsafe_return(app, context, feishu):
    client = TestClient(app, base_url=context.settings.origin)
    assert (
        client.post(
            "/api/session/feishu/start", json={}, headers={"Origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    admin = admin_client(app, context.settings)
    setup_directory(admin, context.settings)
    _, callback, _ = feishu_login(app, context.settings, feishu, "u-wang", return_to="//evil.invalid/x")
    assert callback.headers["location"] == "/workbench"


def test_sync_removal_and_role_revocation_end_sessions(app, context, feishu):
    admin = admin_client(app, context.settings)
    departments = setup_directory(admin, context.settings)
    client, _, _ = feishu_login(app, context.settings, feishu, "u-wang")
    assert client.get("/api/session").status_code == 200

    # 收回财务部默认角色：下一次请求立即失效
    headers = {"Origin": context.settings.origin}
    admin.put(f"/api/identity/departments/{departments['财务部']}/roles", json={"roles": []}, headers=headers)
    assert client.get("/api/session").status_code == 401

    # 个人角色可单独授予；之后从飞书部门移除即停用
    users = {item["name"]: item["id"] for item in admin.get("/api/identity/access").json()["users"]}
    admin.put(
        f"/api/identity/users/{users['王财务']}/roles",
        json={"roles": ["finance"], "customRoles": False},
        headers=headers,
    )
    client, _, _ = feishu_login(app, context.settings, feishu, "u-wang")
    assert client.get("/api/session").status_code == 200
    feishu.members[FINANCE] = []
    admin.post("/api/identity/sync", json={}, headers=headers)
    assert client.get("/api/session").status_code == 401
    row = {item["name"]: item for item in admin.get("/api/identity/access").json()["users"]}["王财务"]
    assert row["active"] is False and row["inactiveReason"] == "已不在同步范围内"


def test_failed_sync_keeps_people_active(app, context, feishu):
    admin = admin_client(app, context.settings)
    setup_directory(admin, context.settings)
    feishu.fail_users = True
    response = admin.post("/api/identity/sync", json={}, headers={"Origin": context.settings.origin})
    assert response.status_code == 502
    overview = admin.get("/api/identity/access").json()
    assert overview["lastSync"]["status"] == "failed"
    assert "通讯录权限" in overview["lastSync"]["error"]
    assert {item["name"] for item in overview["users"] if item["active"]} == {"张采购", "李采购", "王财务"}


def test_custom_roles_replace_department_roles(app, context, feishu):
    admin = admin_client(app, context.settings)
    setup_directory(admin, context.settings)
    headers = {"Origin": context.settings.origin}
    users = {item["name"]: item["id"] for item in admin.get("/api/identity/access").json()["users"]}
    response = admin.put(
        f"/api/identity/users/{users['张采购']}/roles",
        json={"roles": ["viewer"], "customRoles": True},
        headers=headers,
    )
    assert response.status_code == 200
    row = {item["name"]: item for item in admin.get("/api/identity/access").json()["users"]}["张采购"]
    assert row["roles"] == ["viewer"]
    bad = admin.put(
        f"/api/identity/users/{users['张采购']}/roles",
        json={"roles": ["root"], "customRoles": True},
        headers=headers,
    )
    assert bad.status_code == 400


def test_login_options_and_password_switch(env, context, feishu):
    settings = load_settings({**env, "ADMIN_PASSWORD_LOGIN_ENABLED": "false"})
    app = create_app(settings, context.ns, context.engine, feishu=feishu)
    with TestClient(app, base_url=settings.origin) as client:
        assert client.get("/api/session/options").json() == {"feishu": True, "password": False}
        body = {"username": settings.admin_user, "password": settings.admin_password}
        assert client.post("/api/session", json=body, headers={"Origin": settings.origin}).status_code == 403


def test_feishu_config_validation(env):
    with pytest.raises(ValueError):
        load_settings({**env, "FEISHU_APP_ID": "cli_abc"})
    with pytest.raises(ValueError):
        load_settings({**env, "FEISHU_APP_ID": "abc", "FEISHU_APP_SECRET": "s"})
    settings = load_settings({**env, "FEISHU_APP_ID": "cli_abc", "FEISHU_APP_SECRET": "s"})
    assert settings.feishu_redirect_uri == "http://localhost:3000/api/session/feishu/callback"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("/review?status=pending", "/review?status=pending"),
        ("/", "/"),
        ("//evil.invalid", "/workbench"),
        ("https://evil.invalid", "/workbench"),
        ("/login", "/workbench"),
        ("/LOGIN/", "/workbench"),
        ("/%6cogin", "/workbench"),
        ("/tasks/../login", "/workbench"),
        ("/a b", "/workbench"),
        ("/a\\b", "/workbench"),
        (None, "/workbench"),
    ],
)
def test_safe_return_path(value, expected):
    assert safe_return_path(value) == expected


def test_department_tree_and_status_rules():
    parents = {"a": "0", "b": "a", "c": "b", "d": "0"}
    assert subtree(["b"], parents) == {"b", "c"}
    assert ancestors("c", parents) == ["c", "b", "a"]
    assert ancestors("x", {"x": "y", "y": "x"}) == ["x", "y"]
    assert inactive_reason({"is_resigned": True}) == "已离职"
    assert inactive_reason({"is_frozen": True}) == "已被冻结"
    assert inactive_reason({"is_activated": True}) is None
