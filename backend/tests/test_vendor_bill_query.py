"""只读账单版本 3：MockTransport 与隔离数据库验证，不连接 NS。"""

import copy
import json
import time

import httpx
import pytest
from backend.app import create_app
from backend.core.config import Settings, load_settings
from backend.core.errors import ApiError
from backend.integrations.netsuite.client import NetSuite
from backend.modules.source.dto.vendor_bill_query import VendorBillQuery
from backend.modules.source.service.vendor_bill_query_service import VendorBillQueryService
from fastapi.testclient import TestClient
from pydantic import ValidationError

QUERY = {"vendorId": "1", "purchaseOrderIds": ["10"]}


def result():
    return {
        "contractVersion": 3,
        "complete": True,
        "source": "vendor-bill-query",
        "account": "TEST_SB1",
        "query": copy.deepcopy(QUERY),
        "readStartedAt": "2026-10-28T08:00:00Z",
        "readCompletedAt": "2026-10-28T08:00:01Z",
        "status": "OK",
        "vendor": {"id": "1", "code": "V001", "name": "供应商"},
        "purchaseOrders": [
            {
                "id": "10",
                "number": "PO001",
                "vendorId": "1",
                "subsidiaryId": "2",
                "currencyId": "3",
                "currencyName": "人民币",
                "status": "FOUND",
                "bills": [
                    {
                        "billId": "100",
                        "billNumber": "BILL001",
                        "vendorId": "1",
                        "purchaseOrderId": "10",
                        "subPurchaseOrderId": "",
                        "subsidiaryId": "2",
                        "currencyId": "3",
                        "currencyName": "人民币",
                        "approvalStatus": "2",
                        "voided": False,
                        "hasTax": True,
                        "amounts": {
                            "remaining": "200.00",
                            "applied": "1000.10",
                            "payable": "1200.10",
                            "received": "1100.50",
                            "available": "99.60",
                        },
                        "details": {"count": 2, "total": "1100.50"},
                        "consistent": True,
                    }
                ],
            }
        ],
    }


def first_bill(data):
    return data["purchaseOrders"][0]["bills"][0]


def client_for(handler):
    ns = NetSuite(
        Settings(
            account="test-sb1",
            scope=["restlets"],
            vendor_bill_query_script="500",
            vendor_bill_query_deploy="1",
        ),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    ns._cached = ("private-token", time.monotonic() + 300)
    return ns


def query(data, criteria=None):
    ns = client_for(lambda _: httpx.Response(200, json=data))
    try:
        return VendorBillQueryService(ns).query(VendorBillQuery(**(criteria or QUERY)))
    finally:
        ns.close()


def test_exact_read_action_account_and_amount_strings():
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "POST"
        assert request.url.host == "test-sb1.restlets.api.netsuite.com"
        assert dict(request.url.params) == {"script": "500", "deploy": "1"}
        assert json.loads(request.read()) == {"action": "bills", **QUERY}
        return httpx.Response(200, json=result())

    ns = client_for(handle)
    try:
        actual = VendorBillQueryService(ns).query(VendorBillQuery(**QUERY))
        bill = actual.purchaseOrders[0].bills[0]
        assert bill.availableInvoiceAmount == "99.60"
        assert bill.currency == "CNY"
        assert bill.amounts.payable == bill.totalInvoiceAmount == "1200.10"
        assert bill.details.total == "1100.50" and bill.consistent
        assert actual.writeback.allowed is False
        assert actual.queryId and "子采购" in bill.issues[0]
        assert len(calls) == 1
    finally:
        ns.close()


@pytest.mark.parametrize("field", ["vendorId", "purchaseOrderIds"])
@pytest.mark.parametrize(
    "value", [1, True, None, "", " ", " 1 ", "1\n", "V001", "0", "01", "1.0", "1e3", "1 OR 1=1", "1" * 21]
)
def test_invalid_ids_rejected(field, value):
    body = {**QUERY, field: [value] if field == "purchaseOrderIds" else value}
    with pytest.raises(ValidationError):
        VendorBillQuery.model_validate(body)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {**QUERY, "purchaseOrderIds": []},
        {**QUERY, "purchaseOrderIds": ["10", "10"]},
        {**QUERY, "purchaseOrderIds": list(map(str, range(1, 22)))},
        {**QUERY, "purchaseOrderIds": "10"},
        {"vendorId": "1", "purchaseOrderNo": "PO001"},
        {"vendorCode": "V001", "purchaseOrderNo": "PO001"},
        {**QUERY, "purchaseOrderNo": "PO001"},
        {**QUERY, "vendorCode": "V001"},
        {**QUERY, "billId": "100"},
        {**QUERY, "action": "write"},
        {**QUERY, "script": "404"},
    ],
)
def test_request_rejected(body):
    with pytest.raises(ValidationError):
        VendorBillQuery.model_validate(body)


def test_twenty_unique_orders_accepted():
    assert (
        len(VendorBillQuery(vendorId="1", purchaseOrderIds=list(map(str, range(1, 21)))).purchaseOrderIds)
        == 20
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("account", "other"),
        ("query", {**QUERY, "vendorId": "9"}),
        ("query", {**QUERY, "purchaseOrderIds": ["11"]}),
        ("contractVersion", True),
        ("contractVersion", 3.0),
        ("contractVersion", 2),
        ("complete", 1),
        ("complete", "true"),
        ("source", "vendor-invoice-platform"),
        ("status", "VENDOR_NOT_FOUND"),
        ("readStartedAt", "bad"),
        ("readCompletedAt", "2026-10-28T07:00:00Z"),
        ("readStartedAt", "2026-10-28T08:00:00"),
        ("vendor", None),
        ("purchaseOrders", []),
    ],
)
def test_invalid_envelope_never_returned(field, value):
    data = result()
    data[field] = value
    with pytest.raises(ApiError, match="完整性校验失败"):
        query(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("vendorId", "9"),
        ("purchaseOrderId", "11"),
        ("subsidiaryId", "9"),
        ("currencyId", "9"),
        ("currencyName", "美元"),
        ("billId", "0"),
        ("voided", "false"),
        ("hasTax", 1),
        ("consistent", "true"),
        ("approvalStatus", 2),
        ("subPurchaseOrderId", "anything"),
    ],
)
def test_bill_identity_must_stay_in_resolved_scope(field, value):
    data = result()
    first_bill(data)[field] = value
    with pytest.raises(ApiError):
        query(data)


@pytest.mark.parametrize(
    "value",
    [
        0,
        20.5,
        None,
        "NaN",
        "Infinity",
        "1e10",
        "100 CNY",
        "1,000.00",
        "14764.199999999999",
        "20",
        "01.00",
        "10000000000000000.00",
    ],
)
def test_money_requires_exact_bounded_cent_string(value):
    data = result()
    first_bill(data)["amounts"]["received"] = value
    with pytest.raises(ApiError):
        query(data)


@pytest.mark.parametrize("change", ["sum", "available", "flag", "empty_total", "count", "count_bool"])
def test_amount_and_detail_integrity(change):
    data = result()
    bill = first_bill(data)
    if change == "sum":
        bill["amounts"]["applied"] = "1000.11"
    elif change == "available":
        bill["amounts"]["available"] = "99.61"
    elif change == "flag":
        bill["consistent"] = False
    elif change == "empty_total":
        bill["details"]["count"] = 0
    elif change == "count":
        bill["details"]["count"] = -1
    else:
        bill["details"]["count"] = True
    with pytest.raises(ApiError):
        query(data)


@pytest.mark.parametrize("available", ["0.00", "-10.00"])
def test_zero_tax_full_or_over_received_and_inconsistent_details_remain_visible(available):
    data = result()
    bill = first_bill(data)
    bill.update(hasTax=False, approvalStatus="1", voided=True, consistent=False)
    bill["amounts"].update(received="1200.10" if available == "0.00" else "1210.10", available=available)
    actual = query(data)
    output = actual.purchaseOrders[0].bills[0]
    assert output.availableInvoiceAmount == available
    for fragment in ("税额为零", "正向收票", "明细合计不一致", "尚未批准", "已作废"):
        assert any(fragment in issue for issue in output.issues)
    assert not actual.writeback.allowed


@pytest.mark.parametrize("currency", ["美元", "未知币种", ""])
def test_unverified_currency_remains_flagged(currency):
    data = result()
    data["purchaseOrders"][0]["currencyName"] = currency
    first_bill(data)["currencyName"] = currency
    bill = query(data).purchaseOrders[0].bills[0]
    assert any("人民币" in issue for issue in bill.issues)
    assert bill.availableInvoiceAmount == "99.60"


def multi_result():
    data = result()
    order = data["purchaseOrders"][0]
    data["query"]["purchaseOrderIds"] = ["10", "11", "12", "13"]
    data["purchaseOrders"].extend(
        [
            {**order, "id": "11", "status": "NO_BILLS", "bills": []},
            {"id": "12", "status": "PO_NOT_FOUND", "bills": []},
            {**order, "id": "13", "vendorId": "9", "status": "VENDOR_MISMATCH", "bills": []},
        ]
    )
    return data


def test_mixed_multi_order_results_and_multiple_bills():
    data = multi_result()
    data["purchaseOrders"][0]["bills"].append({**first_bill(data), "billId": "101"})
    actual = query(data, data["query"])
    assert [p.status for p in actual.purchaseOrders] == [
        "FOUND",
        "NO_BILLS",
        "PO_NOT_FOUND",
        "VENDOR_MISMATCH",
    ]
    assert len(actual.purchaseOrders[0].bills) == 2
    assert all(p.reason for p in actual.purchaseOrders)
    assert not actual.writeback.allowed


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "missing",
        "extra",
        "reorder",
        "wrong_status",
        "empty_found",
        "missing_with_bills",
        "mismatch_with_bills",
    ],
)
def test_multi_order_completeness(change):
    data = multi_result()
    criteria = copy.deepcopy(data["query"])
    orders = data["purchaseOrders"]
    if change == "duplicate":
        orders[1] = copy.deepcopy(orders[0])
    elif change == "missing":
        orders.pop()
    elif change == "extra":
        orders.append({"id": "14", "status": "PO_NOT_FOUND", "bills": []})
    elif change == "reorder":
        orders.reverse()
    elif change == "wrong_status":
        orders[1]["status"] = "VENDOR_MISMATCH"
    elif change == "empty_found":
        orders[0]["bills"] = []
    elif change == "missing_with_bills":
        orders[2]["bills"] = orders[0]["bills"]
    else:
        orders[3]["bills"] = orders[0]["bills"]
    with pytest.raises(ApiError):
        query(data, criteria)


def test_vendor_not_found_does_not_invent_missing_orders():
    data = result()
    data.update(status="VENDOR_NOT_FOUND", vendor=None, purchaseOrders=[])
    actual = query(data)
    assert actual.status == "VENDOR_NOT_FOUND" and not actual.purchaseOrders
    assert not actual.writeback.allowed


def test_vendor_code_is_display_only_but_id_must_match():
    data = result()
    data["vendor"]["code"] = "RENAMED-VENDOR-CODE"
    assert query(data).vendor.id == "1"
    data["vendor"]["id"] = "2"
    with pytest.raises(ApiError):
        query(data)


def test_duplicate_bill_across_orders_rejected():
    data = result()
    second = copy.deepcopy(data["purchaseOrders"][0])
    second["id"] = "11"
    second["bills"][0]["purchaseOrderId"] = "11"
    data["purchaseOrders"].append(second)
    data["query"]["purchaseOrderIds"].append("11")
    with pytest.raises(ApiError):
        query(data, data["query"])


def test_total_bill_limit_is_global():
    data = result()
    first = data["purchaseOrders"][0]
    template = copy.deepcopy(first_bill(data))
    first["bills"] = [{**template, "billId": str(1000 + i)} for i in range(200)]
    assert len(query(data).purchaseOrders[0].bills) == 200
    data["purchaseOrders"].append(
        {
            **first,
            "id": "11",
            "bills": [{**template, "billId": "999", "purchaseOrderId": "11"}],
        }
    )
    data["query"]["purchaseOrderIds"].append("11")
    with pytest.raises(ApiError):
        query(data, data["query"])


@pytest.mark.parametrize(
    "code", ["QUERY_LIMIT", "INVALID_REQUEST", "INVALID_RESULT", "QUERY_FAILED", "PRIVATE"]
)
def test_error_body_is_not_exposed_or_treated_as_no_bills(code):
    with pytest.raises(ApiError) as caught:
        query({"complete": False, "error": {"code": code, "message": "secret"}})
    assert "secret" not in caught.value.message


def test_missing_config_no_request_and_paired_settings(env):
    ns = NetSuite(Settings())
    try:
        with pytest.raises(ApiError, match="尚未配置"):
            ns.vendor_bill_query(QUERY)
    finally:
        ns.close()
    for values in [
        {"NETSUITE_VENDOR_BILL_QUERY_SCRIPT": "500"},
        {"NETSUITE_VENDOR_BILL_QUERY_SCRIPT": "500&deploy=404", "NETSUITE_VENDOR_BILL_QUERY_DEPLOY": "1"},
    ]:
        with pytest.raises(ValueError):
            load_settings({**env, **values})
    settings = load_settings(
        {**env, "NETSUITE_VENDOR_BILL_QUERY_SCRIPT": "500", "NETSUITE_VENDOR_BILL_QUERY_DEPLOY": "1"}
    )
    assert settings.vendor_bill_query_script == "500"


def test_http_auth_validation_readonly_and_no_write_route(context):
    context.settings.account = "test-sb1"
    calls = []

    def read(criteria):
        calls.append(criteria)
        return result()

    context.ns.vendor_bill_query = read
    with TestClient(create_app(context.settings, context.ns, context.engine)) as client:
        path = "/api/source/vendor-bills/query"
        assert client.post(path, json=QUERY).status_code == 401
        headers = {"Authorization": f"Bearer {context.settings.service_key}"}
        assert client.post(path, json={**QUERY, "action": "write"}, headers=headers).status_code == 400
        assert (
            client.post(
                path, json={"vendorCode": "V001", "purchaseOrderNo": "PO001"}, headers=headers
            ).status_code
            == 400
        )
        assert not calls
        response = client.post(path, json=QUERY, headers=headers)
        assert response.status_code == 200
        assert response.json()["writeback"]["allowed"] is False
        # 现有 SPA 兜底 GET 路由使未注册的 POST 返回 405；没有业务写入口。
        assert client.post("/api/source/vendor-bills/write", json=QUERY, headers=headers).status_code == 405
        assert calls == [QUERY]
        assert context.ns.writes == []
