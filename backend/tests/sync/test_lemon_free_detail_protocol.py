"""免费版只读协议：独立会话、授权账套上下文、明细范围和失败原子性。"""

from types import SimpleNamespace

import httpx
import pytest
from backend.core.errors import ApiError
from backend.integrations.lemon.invoice_client import LemonInvoiceClient
from backend.tests.sync.lemon_detail_fixtures import full_invoice

FREE_ROW = {"asid": 7, "asname": "免费测试账套", "appAsId": "private-free-context"}


def client(handler, host="https://open2.ningmengyun.com"):
    return LemonInvoiceClient(
        SimpleNamespace(lemon_host=host),
        None,
        professional_session_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )


def reply(request, rows=None):
    assert request.method == "GET"
    if request.url.path.endswith("AuthorizationCookie.ashx"):
        assert request.url.host == "api.ningmengyun.com"
        assert dict(request.url.params) == {"token": "private-token"}
        assert "cookie" not in request.headers
        return httpx.Response(
            200, headers={"Set-Cookie": "auth=private-cookie; Domain=.ningmengyun.com; Path=/; Secure"}
        )
    assert request.url.host == "japi.ningmengyun.com"
    assert request.headers["cookie"] == "auth=private-cookie"
    assert "authorization" not in request.headers
    if request.url.path.endswith("TopInfoV2"):
        assert not request.url.params and "appasid" not in request.headers
        return httpx.Response(
            200, json={"state": 1000, "data": {"accountList": rows if rows is not None else [FREE_ROW]}}
        )
    assert request.url.path == "/api/Invoice"
    assert dict(request.url.params) == {
        "appasid": "private-free-context",
        "invoiceId": "1",
        "invoiceType": "1170",
    }
    assert request.headers["appasid"] == "private-free-context"
    return httpx.Response(200, json={"state": 1000, "data": {"invoiceData": full_invoice()["Detail"]}})


def test_free_details_use_selected_context_and_fresh_sessions():
    calls = []
    raw = full_invoice()
    head = {key: value for key, value in raw.items() if key != "Detail"}
    other = {**head, "InvoiceId": 2}

    def handler(request):
        calls.append(request)
        return reply(request)

    upstream = client(handler)
    try:
        for _ in range(2):
            assert upstream.invoice_details("private-token", "7", [head, other], {1}, professional=False) == [
                raw,
                other,
            ]
        assert len(calls) == 6
        assert all("serviceId" not in call.url.params for call in calls)
        assert "Detail" not in head
    finally:
        upstream.close()


@pytest.mark.parametrize(
    "rows", [[], [None], [FREE_ROW, FREE_ROW], [{**FREE_ROW, "appAsId": None}], [{**FREE_ROW, "asid": True}]]
)
def test_invalid_or_revoked_free_account_never_reads_details(rows):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return reply(request, rows)

    upstream = client(handler)
    try:
        with pytest.raises(ApiError):
            upstream.invoice_details("private-token", "7", [full_invoice()], {1}, professional=False)
        assert "/api/Invoice" not in calls
    finally:
        upstream.close()


@pytest.mark.parametrize("status", [302, 403, 500])
def test_detail_failure_does_not_follow_redirect_or_expose_context(status, caplog):
    def handler(request):
        if request.url.path == "/api/Invoice":
            return httpx.Response(
                status, headers={"Location": "https://untrusted.example"}, text="private-error"
            )
        return reply(request)

    upstream = client(handler)
    try:
        with pytest.raises(ApiError, match=f"HTTP {status}") as error:
            upstream.invoice_details("private-token", "7", [full_invoice()], {1}, professional=False)
        assert "private" not in str(error.value) + caplog.text
    finally:
        upstream.close()


def test_empty_selection_and_unsupported_environment_never_request():
    def handler(request):
        pytest.fail("不应请求上游")

    upstream = client(handler, "https://example.invalid")
    try:
        assert upstream.invoice_details("private-token", "7", [], set(), professional=False) == []
        with pytest.raises(ApiError, match="正式环境"):
            upstream.invoice_details("private-token", "7", [full_invoice()], {1}, professional=False)
    finally:
        upstream.close()
