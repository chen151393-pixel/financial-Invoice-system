"""专业版真实响应结构的隔离协议测试；不使用真实凭据、票号或账套。"""

import json
from decimal import Decimal

import httpx
import pytest
from backend.core.errors import ApiError
from backend.integrations.lemon import professional_invoices as protocol
from backend.tests.sync.test_lemon_account_services import PRO_ROW, adapter, reply
from backend.tests.sync.test_lemon_invoices import invoice

PATH = "/api/Invoice/PurchasePagingList"
SUMMARY = {
    "invoiceId": 0,
    "invoiceCategory": 0,
    "number": "",
    "code": "",
    "businessTypeText": "合计",
    "invoiceDate": None,
    "invoiceDateText": "",
}


def pro_invoice(identifier=1, **changes):
    row = invoice(InvoiceId=identifier, Number=f"{identifier:020d}")
    return {**{key[:1].lower() + key[1:]: value for key, value in row.items()}, **changes}


def response(rows, total):
    return {"state": 1000, "data": {"data": rows, "count": total}}


def reader(pages, calls=None, accounts=None):
    def handler(request):
        if request.url.path != PATH:
            return reply(request, rows=accounts)
        if calls is not None:
            calls.append(request)
        page = int(request.url.params["pageIndex"])
        return httpx.Response(200, json=pages[page - 1])

    return protocol.LemonProfessionalInvoices(adapter(handler))


def query(client):
    return client.query("private-user-token", "21", "2026-10-01", "2026-10-16")


def test_selected_account_context_paging_and_summary(monkeypatch):
    monkeypatch.setattr(protocol, "PAGE_SIZE", 2)
    calls = []
    client = reader(
        [
            response([pro_invoice(1), pro_invoice(2), SUMMARY], 3),
            response([pro_invoice(3), SUMMARY], 3),
            response([SUMMARY], 3),
        ],
        calls,
        [{**PRO_ROW, "appAsId": "private-selected-context"}],
    )
    rows = query(client)
    assert [row["InvoiceId"] for row in rows] == [1, 2, 3]
    assert rows[0]["Number"] == "00000000000000000001"
    assert len(calls) == 3
    for page, request in enumerate(calls, 1):
        assert request.method == "POST" and request.url.host == "jproapi.ningmengyun.com"
        assert dict(request.url.params) == {
            "pageIndex": str(page),
            "pageSize": "2",
            "serviceId": "99",
            "appasid": "private-selected-context",
        }
        assert request.headers["appasid"] == "private-selected-context"
        assert request.headers["cookie"] == "auth=private-cookie"
        assert json.loads(request.content) == {
            "startDate": "2026-10-01",
            "endDate": "2026-10-16",
            "invoiceStatus": "0",
            "invoiceType": "0",
            "invoiceVoucherStatus": "0",
            "invoiceIssueDateStatus": "0",
            "invoiceBillStatus": "0",
        }


@pytest.mark.parametrize("rows", [[], [SUMMARY]])
def test_empty_result(rows):
    assert query(reader([response(rows, 0)])) == []


@pytest.mark.parametrize(
    "change",
    [
        {"invoiceId": None},
        {"invoiceId": True},
        {"invoiceId": 0},
        {"invoiceId": -1},
    ],
)
def test_missing_or_invalid_id_is_never_skipped(change):
    with pytest.raises(ApiError):
        query(reader([response([pro_invoice(**change), SUMMARY], 1)]))


@pytest.mark.parametrize(
    "changes",
    [
        {"invoiceId": False},
        {"invoiceCategory": False},
        {"number": "123"},
        {"code": "1"},
        {"businessTypeText": ""},
        {"invoiceDate": "2026-10-10"},
    ],
)
def test_only_verified_summary_signature_is_removed(changes):
    with pytest.raises(ApiError):
        query(reader([response([{**SUMMARY, **changes}], 0)]))


@pytest.mark.parametrize(
    "payload",
    [
        {"state": 401, "data": {}},
        {"state": 1000, "data": []},
        response(None, 0),
        response([None], 1),
        response([], True),
        response([], "0"),
        response([], -1),
        response([], 2001),
        response([], 1),
        response([pro_invoice()], 0),
        response([pro_invoice()] * 102, 102),
        response([SUMMARY, SUMMARY], 0),
    ],
)
def test_invalid_envelope_totals_and_rows(payload):
    with pytest.raises(ApiError):
        query(reader([payload]))


@pytest.mark.parametrize("second", [response([pro_invoice(1)], 2), response([], 2), response([], 1)])
def test_duplicate_missing_page_or_changed_total(second, monkeypatch):
    monkeypatch.setattr(protocol, "PAGE_SIZE", 1)
    with pytest.raises(ApiError):
        query(reader([response([pro_invoice(1)], 2), second]))


@pytest.mark.parametrize("accounts", [[], [{**PRO_ROW, "appAsId": None}]])
def test_revoked_or_missing_selected_context_never_reads_invoices(accounts):
    calls = []
    with pytest.raises(ApiError):
        query(reader([], calls, accounts))
    assert calls == []


def test_decimal_response_is_not_float():
    calls = []

    def handler(request):
        if request.url.path != PATH:
            return reply(request)
        calls.append(request)
        payload = response([pro_invoice()] if len(calls) == 1 else [], 1)
        return httpx.Response(200, content=json.dumps(payload).replace('"100.00"', "100.00"))

    row = query(protocol.LemonProfessionalInvoices(adapter(handler)))[0]
    assert type(row["Amount"]) is Decimal and row["Amount"] == Decimal("100.00")


@pytest.mark.parametrize("status", [302, 401, 403, 500])
def test_invoice_failure_never_redirects_or_exposes_context(status, caplog):
    def handler(request):
        if request.url.path != PATH:
            return reply(request)
        return httpx.Response(
            status, headers={"Location": "https://untrusted.example"}, text="private-response"
        )

    with pytest.raises(ApiError, match=f"HTTP {status}") as error:
        query(protocol.LemonProfessionalInvoices(adapter(handler)))
    assert "private" not in str(error.value) + caplog.text


def test_timeout_stops_pagination(monkeypatch):
    ticks = iter([0, 121])
    monkeypatch.setattr(protocol.time, "monotonic", lambda: next(ticks))
    with pytest.raises(ApiError, match="时间过长"):
        reader([])._pages(None, {}, "2026-10-01", "2026-10-16")
