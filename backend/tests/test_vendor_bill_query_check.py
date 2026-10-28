"""抽样工具按母单核对状态、账单归属和金额，读取失败不能标记通过。"""

import json
from types import SimpleNamespace

import httpx
import pytest
from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.modules.source.dto.vendor_bill_query import VendorBillQuery
from pydantic import ValidationError
from scripts.ns_vendor_bill_query_check import Case, Expected, QueryApi, compare, run


def sample():
    return SimpleNamespace(
        status="OK",
        purchaseOrders=[
            SimpleNamespace(
                id="10",
                status="FOUND",
                bills=[
                    SimpleNamespace(
                        billId="100",
                        totalInvoiceAmount="20.00",
                        receivedInvoiceAmount="0.00",
                        availableInvoiceAmount="20.00",
                    )
                ],
            )
        ],
    )


def expected():
    return Expected(
        status="OK",
        purchaseOrders=[
            {
                "id": "10",
                "status": "FOUND",
                "bills": [
                    {
                        "billId": "100",
                        "totalInvoiceAmount": "20",
                        "receivedInvoiceAmount": "0",
                        "availableInvoiceAmount": "20.0",
                    }
                ],
            }
        ],
    )


def test_equal_decimal_not_equal_string():
    assert compare(sample(), expected()) == ("MATCH", [])
    assert compare(sample(), None)[0] == "NOT_COMPARED"


@pytest.mark.parametrize("change", ["status", "order_id", "order_status", "id", "money", "missing"])
def test_discrepancy(change):
    value = sample()
    order = value.purchaseOrders[0]
    if change == "status":
        value.status = "VENDOR_NOT_FOUND"
    elif change == "order_id":
        order.id = "11"
    elif change == "order_status":
        order.status = "NO_BILLS"
    elif change == "id":
        order.bills[0].billId = "101"
    elif change == "missing":
        value.purchaseOrders = []
    else:
        order.bills[0].availableInvoiceAmount = "19.99"
    assert compare(value, expected())[0] == "DIFFERENT"


def test_bill_moved_to_another_order_is_not_match():
    value = sample()
    reference = expected()
    reference.purchaseOrders.append(
        reference.purchaseOrders[0].model_copy(update={"id": "11", "status": "NO_BILLS", "bills": []})
    )
    value.purchaseOrders.append(SimpleNamespace(id="11", status="FOUND", bills=value.purchaseOrders[0].bills))
    value.purchaseOrders[0].bills = []
    value.purchaseOrders[0].status = "NO_BILLS"
    assert compare(value, reference)[0] == "DIFFERENT"


@pytest.mark.parametrize("kind", ["order", "bill"])
def test_reference_duplicate_identity_rejected(kind):
    data = expected().model_dump()
    if kind == "order":
        data["purchaseOrders"].append(data["purchaseOrders"][0])
    else:
        order = data["purchaseOrders"][0]
        order["bills"].append(order["bills"][0])
    with pytest.raises(ValidationError):
        Expected.model_validate(data)


def test_query_error_not_match():
    class Service:
        def query(self, criteria):
            raise ApiError(502, "查询失败")

    cases = [Case(name="只读核对", query={"vendorId": "1", "purchaseOrderIds": ["10"]})]
    assert run(Service(), cases)[0]["verdict"] == "ERROR"


def test_old_sample_query_rejected():
    with pytest.raises(ValidationError):
        Case(name="旧参数", query={"vendorId": "1", "purchaseOrderNo": "PO001"})


def test_tool_calls_authenticated_api_and_rechecks_account():
    criteria = VendorBillQuery(vendorId="1", purchaseOrderIds=["10"])
    response = {
        "contractVersion": 3,
        "complete": True,
        "source": "vendor-bill-query",
        "account": "test-sb1",
        "query": criteria.model_dump(),
        "readStartedAt": "2026-10-28T08:00:00Z",
        "readCompletedAt": "2026-10-28T08:00:01Z",
        "status": "VENDOR_NOT_FOUND",
        "vendor": None,
        "purchaseOrders": [],
        "queryId": "sample",
        "reason": "未找到",
        "warnings": [],
        "writeback": {"allowed": False, "reason": "只读"},
    }
    calls = []

    def handle(request):
        calls.append(request)
        assert str(request.url) == "http://localhost:3000/api/source/vendor-bills/query"
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer test-service-key"
        assert json.loads(request.read()) == criteria.model_dump()
        return httpx.Response(200, json=response)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        api = QueryApi(Settings(account="test-sb1", service_key="test-service-key"), client)
        assert api.query(criteria).status == "VENDOR_NOT_FOUND"
        response["account"] = "other"
        with pytest.raises(ApiError, match="账套不一致"):
            api.query(criteria)
    assert len(calls) == 2


@pytest.mark.parametrize("status", [302, 401, 500])
def test_tool_no_retry_redirect_or_raw_error_exposure(status):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, text="secret", headers={"location": "https://other.invalid"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        api = QueryApi(Settings(account="test-sb1", service_key="test-key"), client)
        with pytest.raises(ApiError) as caught:
            api.query(VendorBillQuery(vendorId="1", purchaseOrderIds=["10"]))
        assert "secret" not in caught.value.message
    assert len(calls) == 1
