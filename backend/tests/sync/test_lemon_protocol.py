"""正式 open2 请求形状与分页异常，不访问真实柠檬云。"""

from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from backend.core.errors import ApiError
from backend.integrations.lemon.invoice_client import LemonInvoiceClient


def client(handler):
    return LemonInvoiceClient(
        SimpleNamespace(lemon_host="https://open2.ningmengyun.com"),
        SimpleNamespace(app_token=lambda: "global-secret"),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_official_user_token_account_and_query_headers():
    calls = []

    def handler(request):
        calls.append(request)
        path = request.url.path
        if path.endswith("GetSpecificUserToken"):
            assert request.headers["Authorization"] == "Bearer global-secret"
            assert dict(request.url.params) == {"userid": "13800000001", "isOem": "false"}
            data = {"access_token": "user-secret", "expires_in": 120}
        elif path.endswith("GetAccountSets"):
            assert request.headers["Authorization"] == "Bearer user-secret"
            data = {"rows": [{"AsId": 7, "AsName": "测试账套", "TaxPayerPassword": "not-for-browser"}]}
        else:
            assert request.headers["Authorization"] == "Bearer user-secret"
            assert request.headers["asid"] == "7"
            assert request.method == "POST" and not request.content
            assert dict(request.url.params) == {
                "invoiceCategory": "10080",
                "startDate": "2026-10-01",
                "endDate": "2026-10-16",
                "number": "",
                "invoiceType": "0",
                "invoiceStatus": "0",
                "name": "",
                "page": str(len(calls) - 2),
                "rows": "100",
            }
            if request.url.params["page"] == "1":
                return httpx.Response(
                    200,
                    content='{"State":1000,"Data":{"List":[{"InvoiceId":1,"Amount":12345678901234.12}],"Count":1}}',
                )
            data = {"List": [], "Count": 1}
        return httpx.Response(200, json={"State": 1000, "Data": data})

    upstream = client(handler)
    token = upstream.user_token("13800000001")
    assert upstream.accounts(token) == [{"asid": "7", "name": "测试账套"}]
    rows = upstream.invoices(token, "7", "2026-10-01", "2026-10-16")
    assert rows[0]["Amount"] == Decimal("12345678901234.12")
    assert len(calls) == 4
    upstream.close()


@pytest.mark.parametrize(
    "data", [{}, {"list": []}, {"List": None}, {"List": [{"InvoiceId": True}]}, {"List": [{}]}]
)
def test_malformed_list_is_not_empty_success(data):
    with pytest.raises(ApiError):
        client(lambda req: httpx.Response(200, json={"State": 1000, "Data": data})).invoices(
            "token", "7", "2026-10-01", "2026-10-16"
        )


def test_repeat_page_and_later_failure_never_return_partial_batch():
    for fail in (False, True):

        def handler(request):
            if fail and request.url.params["page"] == "2":
                return httpx.Response(401, json={"Msg": "secret"})
            return httpx.Response(200, json={"State": 1000, "Data": {"List": [{"InvoiceId": 1}]}})

        with pytest.raises(ApiError) as error:
            client(handler).invoices("secret", "7", "2026-10-01", "2026-10-16")
        assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "payload", [{"State": 2000, "Msg": "secret", "Data": {}}, {"State": 1000, "Data": []}]
)
def test_bad_envelope_and_upstream_message_are_not_exposed(payload):
    with pytest.raises(ApiError) as error:
        client(lambda req: httpx.Response(200, json=payload)).user_token("13800000001")
    assert "secret" not in str(error.value)


def test_page_limit_rejects_instead_of_truncating():
    def handler(request):
        page = int(request.url.params["page"])
        return httpx.Response(
            200, json={"State": 1000, "Data": {"List": [{"InvoiceId": page * 100 + n} for n in range(100)]}}
        )

    with pytest.raises(ApiError, match="2000"):
        client(handler).invoices("token", "7", "2026-10-01", "2026-10-16")


def test_required_empty_query_keys_reach_upstream_authorization(caplog):
    def handler(request):
        # 复现官方无凭证探测：缺查询键时路由 404，完整请求才进入授权检查。
        params = dict(request.url.params)
        if not {"number", "name", "invoiceType"} <= params.keys():
            return httpx.Response(404, json={"Message": "No matching resource"})
        return httpx.Response(401, json={"Message": "Unauthorized"})

    upstream = client(handler)
    try:
        with pytest.raises(ApiError, match="HTTP 401"):
            upstream.invoices("test-token", "7", "2026-10-01", "2026-10-16")
    finally:
        upstream.close()
    assert "operation=invoices" in caplog.text
    assert "upstream_status=401" in caplog.text
