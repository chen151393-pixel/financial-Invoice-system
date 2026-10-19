"""只读详情的所选账套、失败、截止时间和默认版边界。"""

from copy import deepcopy

import httpx
import pytest
from backend.core.errors import ApiError
from backend.integrations.lemon import professional_invoice_details as protocol
from backend.integrations.lemon.invoice_client import LemonInvoiceClient
from backend.tests.sync.lemon_detail_fixtures import full_invoice
from backend.tests.sync.test_lemon_account_services import PRO_ROW, adapter, reply


def enrich(payload, calls=None, records=None, accounts=None):
    def handler(request):
        if request.url.path != "/api/Invoice":
            return reply(request, rows=accounts)
        if calls is not None:
            calls.append(request)
        return httpx.Response(200, json=payload)

    return protocol.LemonProfessionalInvoiceDetails(adapter(handler)).enrich(
        "private-user-token", "21", records or [full_invoice()], {1}
    )


def test_selected_context_and_only_requested_ids():
    calls = []
    raw = full_invoice()
    other = full_invoice(InvoiceId=2, Number="2")
    rows = enrich(
        {"state": 1000, "data": {"invoiceData": raw["Detail"]}},
        calls,
        [raw, other],
        [{**PRO_ROW, "appAsId": "private-selected-context"}],
    )
    assert rows == [raw, other] and len(calls) == 1
    request = calls[0]
    assert request.method == "GET" and request.url.host == "jproapi.ningmengyun.com"
    assert dict(request.url.params) == {
        "serviceId": "99",
        "appasid": "private-selected-context",
        "invoiceId": "1",
        "invoiceType": "1170",
    }
    assert request.headers["appasid"] == "private-selected-context"
    assert request.headers["cookie"] == "auth=private-cookie"


@pytest.mark.parametrize(
    "payload",
    [
        {"state": 401, "data": {}},
        {"state": 1000, "data": []},
        {"state": 1000, "data": {}},
        {"state": 1000, "data": {"invoiceData": {}}},
        {"state": 1000, "data": {"invoiceData": {"invoiceEntries": [None]}}},
        {"state": 1000, "data": {"invoiceData": {"invoiceEntries": [{}] * 10001}}},
    ],
)
def test_missing_or_malformed_details_are_not_success(payload):
    with pytest.raises(ApiError):
        enrich(payload)


@pytest.mark.parametrize("accounts", [[], [{**PRO_ROW, "appAsId": None}]])
def test_revoked_account_or_missing_context_stops_read(accounts):
    calls = []
    with pytest.raises(ApiError):
        enrich({}, calls, accounts=accounts)
    assert not calls


def test_empty_selection_no_session_and_default_edition_stays_pending():
    raw = full_invoice()
    raw.pop("Detail")
    client = protocol.LemonProfessionalInvoiceDetails(None)
    assert client.enrich("token", "7", [raw], set()) == [raw]
    assert LemonInvoiceClient.invoice_details(None, "token", "7", [raw], {1}, professional=False) == [raw]


def test_deadline_prevents_detail_call(monkeypatch):
    times = iter([0, 121])
    monkeypatch.setattr(protocol.time, "monotonic", lambda: next(times))
    calls = []
    with pytest.raises(ApiError, match="时间过长"):
        enrich({}, calls)
    assert not calls


def test_later_detail_failure_aborts_whole_read():
    raw = full_invoice()
    second = deepcopy(raw)
    second["InvoiceId"] = 2
    calls = []

    def handler(request):
        if request.url.path != "/api/Invoice":
            return reply(request)
        calls.append(request)
        return (
            httpx.Response(200, json={"state": 1000, "data": {"invoiceData": raw["Detail"]}})
            if len(calls) == 1
            else httpx.Response(503)
        )

    with pytest.raises(ApiError, match="HTTP 503"):
        protocol.LemonProfessionalInvoiceDetails(adapter(handler)).enrich(
            "private-user-token", "21", [raw, second], {1, 2}
        )
    assert len(calls) == 2
