"""通过真实 HTTP 适配与隔离 API 验证专业版自动发现，不访问柠檬云生产环境。"""

from types import SimpleNamespace

import httpx
import pytest
from backend.core.errors import ApiError
from backend.modules.sync.service.lemon_account_service import LemonAccountService
from backend.tests.sync.test_lemon_invoices import BASE, body
from backend.tests.sync.test_lemon_invoices import setup as setup
from backend.tests.sync.test_lemon_protocol import client


def discovery(handler):
    upstream = client(handler)
    service = LemonAccountService(SimpleNamespace(engine=None), upstream)
    return service, upstream


def ok(data):
    return httpx.Response(200, json={"State": 1000, "Data": data})


def test_automatic_services_are_deduplicated_and_free_accounts_are_not_substituted():
    calls = []

    def handler(request):
        assert request.headers["Authorization"] == "Bearer user-token"
        assert request.method == "POST" and not request.content
        calls.append((request.url.path, dict(request.url.params)))
        if request.url.path.endswith("GetAllPermissions"):
            assert request.headers["asid"] == "7"
            return ok(
                {
                    "rows": [
                        {"AsId": 7, "ServiceId": 0},
                        {"AsId": 21, "ServiceId": 99},
                        {"as_id": 22, "ServiceId": 99},
                        {"as_id": 23, "ServiceId": 100},
                    ]
                }
            )
        service_id = request.url.params.get("serviceId")
        if service_id == "99":
            return ok({"rows": [{"AsId": 21, "AsName": "专业账套甲"}, {"AsId": 22, "AsName": "专业账套乙"}]})
        if service_id == "100":
            return ok({"rows": [{"AsId": 22, "AsName": "专业账套乙"}, {"AsId": 23, "AsName": "专业账套丙"}]})
        assert not request.url.params
        return ok({"rows": [{"AsId": 7, "AsName": "免费账套"}]})

    service, upstream = discovery(handler)
    try:
        result = service.authorized_accounts("user-token")
    finally:
        upstream.close()
    assert {row["asid"] for row in result} == {"21", "22", "23"}
    assert len(result) == 3 and len(calls) == 4
    assert {params["serviceId"] for _, params in calls if params} == {"99", "100"}


@pytest.mark.parametrize("defaults", [[], [{"AsId": 7, "AsName": "免费账套"}]])
def test_professional_service_is_discovered_even_with_no_default_accounts(defaults):
    def handler(request):
        if request.url.path.endswith("GetAllPermissions"):
            assert request.headers.get("asid") == ("7" if defaults else None)
            return ok({"rows": [{"AsId": 21, "ServiceId": 99}]})
        if request.url.params.get("serviceId") == "99":
            return ok({"rows": [{"AsId": 21, "AsName": "专业账套"}]})
        return ok({"rows": defaults})

    service, upstream = discovery(handler)
    try:
        assert service.authorized_accounts("token") == [{"asid": "21", "name": "专业账套"}]
    finally:
        upstream.close()


@pytest.mark.parametrize("service_id", [None, 0])
def test_free_only_account_keeps_existing_query(service_id):
    def handler(request):
        if request.url.path.endswith("GetAllPermissions"):
            return ok({"rows": [{"AsId": 7, "ServiceId": service_id}]})
        assert not request.url.params
        return ok({"rows": [{"AsId": 7, "AsName": "免费账套"}]})

    service, upstream = discovery(handler)
    try:
        assert service.authorized_accounts("token") == [{"asid": "7", "name": "免费账套"}]
    finally:
        upstream.close()


@pytest.mark.parametrize("stage", ["permissions", "service"])
def test_discovery_failure_does_not_fall_back_to_default_accounts(stage):
    def handler(request):
        if request.url.path.endswith("GetAllPermissions"):
            if stage == "permissions":
                return httpx.Response(403)
            return ok({"rows": [{"AsId": 21, "ServiceId": 99}]})
        if request.url.params:
            return httpx.Response(403)
        return ok({"rows": [{"AsId": 7, "AsName": "免费账套"}]})

    service, upstream = discovery(handler)
    try:
        with pytest.raises(ApiError, match="HTTP 403"):
            service.authorized_accounts("token")
    finally:
        upstream.close()


@pytest.mark.parametrize("second", ["empty", "failure", "conflict"])
def test_professional_empty_partial_failure_and_conflicting_account_names(second):
    def handler(request):
        if request.url.path.endswith("GetAllPermissions"):
            return ok({"rows": [{"AsId": 21, "ServiceId": 10}, {"AsId": 22, "ServiceId": 20}]})
        service_id = request.url.params.get("serviceId")
        if service_id == "20" and second == "failure":
            return httpx.Response(502)
        if service_id:
            if second == "empty":
                return ok({"rows": []})
            name = "不同名称" if service_id == "20" else "专业账套"
            return ok({"rows": [{"AsId": 21, "AsName": name}]})
        return ok({"rows": [{"AsId": 7, "AsName": "免费账套"}]})

    service, upstream = discovery(handler)
    try:
        if second == "empty":
            assert service.authorized_accounts("token") == []
        else:
            with pytest.raises(ApiError, match="HTTP 502" if second == "failure" else "不一致"):
                service.authorized_accounts("token")
    finally:
        upstream.close()


@pytest.mark.parametrize(
    "rows",
    [
        None,
        [{}],
        [None],
        [{"AsId": True, "ServiceId": 1}],
        [{"AsId": 7, "ServiceId": True}],
        [{"AsId": 7, "ServiceId": -1}],
        [{"AsId": 7, "ServiceId": "99"}],
        [{"AsId": 7, "ServiceId": 2147483648}],
    ],
)
def test_invalid_permissions_are_not_treated_as_free_only(rows):
    upstream = client(lambda request: ok({"rows": rows}))
    try:
        with pytest.raises(ApiError):
            upstream.account_service_ids("token", "7")
    finally:
        upstream.close()


def test_query_select_and_pull_all_use_current_professional_service(setup):
    calls, permissions = [], [{"AsId": 21, "ServiceId": 99}]

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("GetSpecificUserToken"):
            return ok({"access_token": "user-token"})
        if request.url.path.endswith("GetAllPermissions"):
            return ok({"rows": permissions})
        if request.url.path.endswith("GetAccountSets"):
            rows = [{"AsId": 7, "AsName": "免费账套"}]
            if request.url.params.get("serviceId") == "99":
                rows = [{"AsId": 21, "AsName": "专业账套"}]
            return ok({"rows": rows})
        assert request.url.path.endswith("GetInvoice")
        assert request.headers["asid"] == "21"
        return ok({"List": []})

    upstream = setup.upstream
    adapter = client(handler)
    # 应用的 Service 复用此注入对象；只替换 HTTP 适配方法，保留真实路由和数据库。
    upstream.user_token = adapter.user_token
    upstream.accounts = adapter.accounts
    upstream.account_service_ids = adapter.account_service_ids
    upstream.invoices = adapter.invoices
    try:
        response = setup.client.post(BASE + "/accounts/query", json={})
        assert response.status_code == 200
        assert response.json() == {"items": [{"asid": "21", "name": "专业账套"}]}
        assert setup.client.post(BASE + "/account", json={"asid": "7"}).status_code == 403
        selected = setup.client.post(BASE + "/account", json={"asid": "21"})
        assert selected.status_code == 200 and selected.json()["selected"]["asid"] == "21"
        assert setup.client.get(BASE + "/invoices/configuration").json()["selected"]["asid"] == "21"
        response = setup.client.post(BASE + "/invoices/pull-save", json=body(asid="21"))
        assert response.status_code == 200 and response.json()["status"] == "completed"
        assert len([request for request in calls if request.url.params.get("serviceId") == "99"]) == 4
        permissions.clear()
        calls.clear()
        revoked = setup.client.post(BASE + "/invoices/pull-save", json=body(asid="21"))
        assert revoked.status_code == 403
        assert not any(request.url.path.endswith("GetInvoice") for request in calls)
    finally:
        adapter.close()
