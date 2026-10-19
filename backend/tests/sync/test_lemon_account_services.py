"""专业版真实协议形状的隔离测试；不将模拟结果作为真实联调记录。"""

from types import SimpleNamespace

import httpx
import pytest
from backend.core.errors import ApiError
from backend.integrations.lemon.professional_accounts import LemonProfessionalAccounts
from backend.modules.sync.service.lemon_account_service import LemonAccountService
from backend.tests.sync.test_lemon_invoices import BASE, body
from backend.tests.sync.test_lemon_invoices import setup as setup

PRO_ROW = {"asid": 21, "asname": "专业账套", "appAsId": "private-account-context"}


def adapter(handler):
    return LemonProfessionalAccounts(
        SimpleNamespace(lemon_host="https://open2.ningmengyun.com"),
        lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )


def reply(request, *, available=True, service_id=99, rows=None):
    path = request.url.path
    if path.endswith("AuthorizationCookie.ashx"):
        assert request.url.host == "api.ningmengyun.com"
        assert dict(request.url.params) == {"token": "private-user-token"}
        assert "cookie" not in request.headers
        return httpx.Response(
            200, headers={"Set-Cookie": "auth=private-cookie; Domain=.ningmengyun.com; Path=/; Secure"}
        )
    assert "authorization" not in request.headers
    assert request.headers["cookie"] == "auth=private-cookie"
    if path.endswith("haveProServiceInfo"):
        return httpx.Response(200, json={"statusCode": True, "data": available})
    if path.endswith("/redirect/info"):
        assert dict(request.url.params) == {"appId": "1060", "virtualAppId": "1062", "productType": "acc"}
        return httpx.Response(
            200,
            json={
                "statusCode": True,
                "data": {
                    "serviceId": service_id,
                    "appasid": "private-account-context",
                    "url": "https://untrusted.example",
                },
            },
        )
    assert request.url.host == "jproapi.ningmengyun.com"
    assert path == "/api/AccountSetOnlyAuth/TopInfoV2"
    assert dict(request.url.params) == {"serviceId": str(service_id), "appasid": "private-account-context"}
    return httpx.Response(
        200, json={"state": 1000, "data": {"accountList": [PRO_ROW] if rows is None else rows}}
    )


def test_verified_protocol_uses_service_context_and_fresh_cookie_jar():
    calls = []

    def handler(request):
        assert request.method == "GET"
        calls.append(request)
        return reply(request)

    upstream = adapter(handler)
    for _ in range(2):
        assert upstream.query("private-user-token") == [
            {"asid": "21", "name": "专业账套", "edition": "professional"}
        ]
    assert len(calls) == 8
    assert all(request.url.host != "untrusted.example" for request in calls)


@pytest.mark.parametrize("available", [False, True])
def test_empty_professional_results_are_not_free_results(available):
    upstream = adapter(lambda request: reply(request, available=available, rows=[]))
    assert upstream.query("private-user-token") == ([] if available else None)


@pytest.mark.parametrize("value", [None, 0, -1, True, "99", 2147483648])
def test_invalid_service_context_is_rejected(value):
    upstream = adapter(lambda request: reply(request, service_id=value))
    with pytest.raises(ApiError, match="服务 ID"):
        upstream.query("private-user-token")


@pytest.mark.parametrize(
    "rows",
    [
        [{}],
        [None],
        [{**PRO_ROW, "asid": True}],
        [{**PRO_ROW, "asname": ""}],
        [PRO_ROW, PRO_ROW],
        [PRO_ROW] * 1001,
    ],
)
def test_invalid_or_duplicate_accounts_never_succeed(rows):
    with pytest.raises(ApiError):
        adapter(lambda request: reply(request, rows=rows)).query("private-user-token")


@pytest.mark.parametrize(
    "path", ["AuthorizationCookie.ashx", "haveProServiceInfo", "/redirect/info", "TopInfoV2"]
)
@pytest.mark.parametrize("status", [302, 401, 403, 500])
def test_failures_do_not_follow_redirect_or_fall_back(path, status, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith(path):
            return httpx.Response(
                status, headers={"Location": "https://untrusted.example/private"}, text="private-response"
            )
        return reply(request)

    with pytest.raises(ApiError, match=f"HTTP {status}") as error:
        adapter(handler).query("private-user-token")
    assert calls[-1].url.path.endswith(path)
    assert "private" not in caplog.text + str(error.value)


@pytest.mark.parametrize("data", [None, "false", {}, 0])
def test_missing_or_malformed_availability_is_not_no_service(data):
    def handler(request):
        if request.url.path.endswith("haveProServiceInfo"):
            return httpx.Response(200, json={"statusCode": True, "data": data})
        return reply(request)

    with pytest.raises(ApiError):
        adapter(handler).query("private-user-token")


def test_default_accounts_only_used_after_explicit_no_service():
    calls = []
    client = SimpleNamespace(
        professional_accounts=lambda token: None,
        accounts=lambda token: calls.append(token) or [{"asid": "7", "name": "默认账套"}],
    )
    service = LemonAccountService(SimpleNamespace(engine=None), client)
    assert service.authorized_accounts("token") == [{"asid": "7", "name": "默认账套"}]
    client.professional_accounts = lambda token: []
    assert service.authorized_accounts("token") == []
    assert calls == ["token"]


def test_query_select_and_revoke(setup):
    rows = [PRO_ROW]
    upstream = adapter(lambda request: reply(request, rows=rows))
    setup.upstream.professional_accounts = upstream.query
    response = setup.client.post(BASE + "/accounts/query", json={})
    assert response.status_code == 200
    assert response.json() == {"items": [{"asid": "21", "name": "专业账套"}]}
    assert setup.client.post(BASE + "/account", json={"asid": "7"}).status_code == 403
    selected = setup.client.post(BASE + "/account", json={"asid": "21"})
    assert selected.status_code == 200 and selected.json()["selected"]["asid"] == "21"
    rows.clear()
    assert setup.client.post(BASE + "/invoices/pull-save", json=body(asid="21")).status_code == 403
    assert setup.upstream.pulls == 0
