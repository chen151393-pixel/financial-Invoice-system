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
            # 每页都返回同一张票：重复页必须整批拒收
            return httpx.Response(
                200, json={"State": 1000, "Data": {"List": [{"InvoiceId": 1}], "Count": 150}}
            )

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
        rows = [{"InvoiceId": page * 100 + n} for n in range(100)]
        return httpx.Response(200, json={"State": 1000, "Data": {"List": rows, "Count": 2001}})

    with pytest.raises(ApiError, match="2000") as error:
        client(handler).invoices("token", "7", "2026-10-01", "2026-10-16")
    assert error.value.code == "lemon_range_limit"


# 2026-10-29 免费版实测的合计行：零编号、无号码和日期，价税合计为千分位文本
SUMMARY = {
    "InvoiceId": 0,
    "InvoiceCategory": 0,
    "InvoiceType": 0,
    "BusinessTypeText": "合计",
    "Number": None,
    "Code": None,
    "InvoiceDate": None,
    "InvoiceDateText": "",
    "Amount": 3768288.73,
    "AdValoremTaxTotals": "4,213,116.85",
}


def paged(pages, count):
    def handler(request):
        page = int(request.url.params["page"])
        rows = pages[page - 1] if page <= len(pages) else [SUMMARY]
        return httpx.Response(200, json={"State": 1000, "Data": {"List": rows, "Count": count}})

    return handler


def invoice(identifier, gross="1.00"):
    return {"InvoiceId": identifier, "Number": f"{identifier:020d}", "AdValoremTaxTotals": gross}


def test_summary_row_on_last_page_and_trailing_pages_is_not_an_invoice():
    first = [invoice(n) for n in range(1, 101)]
    second = [invoice(n) for n in range(101, 137)] + [SUMMARY]
    calls = []
    handler = paged([first, second], 136)
    rows = client(lambda request: calls.append(request) or handler(request)).invoices(
        "token", "7", "2026-10-01", "2026-10-28"
    )
    assert [row["InvoiceId"] for row in rows] == list(range(1, 137))
    assert len(calls) == 3


def test_empty_range_returns_only_summary():
    assert client(paged([[SUMMARY]], 0)).invoices("token", "7", "2026-10-01", "2026-10-28") == []


@pytest.mark.parametrize(
    "changed",
    [
        {"BusinessTypeText": "办公费"},
        {"Number": "00000000000000000001"},
        {"InvoiceDateText": "2026-10-03"},
        {"InvoiceCategory": 10080},
    ],
)
def test_zero_id_row_that_is_not_exact_summary_is_rejected(changed):
    with pytest.raises(ApiError, match="编号缺失"):
        client(paged([[invoice(1), {**SUMMARY, **changed}]], 2)).invoices(
            "token", "7", "2026-10-01", "2026-10-28"
        )


def test_summary_in_middle_of_page_is_rejected():
    with pytest.raises(ApiError):
        client(paged([[SUMMARY, invoice(1)]], 1)).invoices("token", "7", "2026-10-01", "2026-10-28")


@pytest.mark.parametrize(
    ("pages", "count"),
    [([[invoice(1)], [SUMMARY]], 2), ([[invoice(n) for n in range(1, 101)], [invoice(101), SUMMARY]], 100)],
)
def test_rows_must_match_count(pages, count):
    with pytest.raises(ApiError, match="总数不一致"):
        client(paged(pages, count)).invoices("token", "7", "2026-10-01", "2026-10-28")


def test_count_change_between_pages_rejects_batch():
    counts = iter((101, 102))

    def handler(request):
        page = int(request.url.params["page"])
        rows = [invoice(n) for n in range(1, 101)] if page == 1 else [invoice(101), SUMMARY]
        return httpx.Response(200, json={"State": 1000, "Data": {"List": rows, "Count": next(counts)}})

    with pytest.raises(ApiError, match="总数在分页期间变化"):
        client(handler).invoices("token", "7", "2026-10-01", "2026-10-28")


@pytest.mark.parametrize(
    ("gross", "expected"),
    [
        ("1,234.00", "1234.00"),
        ("-12,345,678.90", "-12345678.90"),
        ("999.10", "999.10"),
        # 不规范分组保持原文，由 invoice 金额校验拒收
        ("1,23.00", "1,23.00"),
        ("1,234", "1,234"),
        ("12,3456.00", "12,3456.00"),
    ],
)
def test_grouped_gross_text_is_normalized_strictly(gross, expected):
    rows = client(paged([[invoice(1, gross), SUMMARY]], 1)).invoices("token", "7", "2026-10-01", "2026-10-28")
    assert rows[0]["AdValoremTaxTotals"] == expected


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
