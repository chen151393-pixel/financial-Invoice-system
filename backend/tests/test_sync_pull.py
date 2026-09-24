"""同步拉取契约：身份、只读、分页、精度及上游失败。"""

from decimal import Decimal

import pytest
from backend.app import create_app
from backend.core.config import load_settings
from backend.core.errors import ApiError
from fastapi.testclient import TestClient


@pytest.fixture
def sync_api(context, tmp_path):
    settings = context.settings
    settings.record_types = ["purchaseOrder", "customrecord_subpo", "customrecord_customs"]
    settings.pl_lookup = {
        "purchase": {"type": "customrecord_subpo"},
        "customs": {"type": "customrecord_customs"},
    }
    settings.client_id = "test"
    settings.certificate_id = "test"
    settings.private_key = tmp_path / "key"
    settings.private_key.write_text("fake", encoding="utf-8")
    calls = []

    def request(method, record_type, record_id=None, **kwargs):
        calls.append((method, record_type, record_id, kwargs))
        assert method == "GET"
        assert kwargs["exact_numbers"] is True
        if record_id:
            return {"data": {"id": record_id, "tranId": "PO001", "amount": Decimal("123.4500")}}
        return {"data": {"items": [{"id": "1"}], "hasMore": True}}

    context.ns.request = request
    with TestClient(create_app(settings, context.ns, context.engine)) as client:
        headers = {"Authorization": f"Bearer {settings.service_key}"}
        yield client, headers, context, calls


@pytest.mark.parametrize(
    "kind,record_type",
    [
        ("purchase-orders", "purchaseOrder"),
        ("sub-purchase-orders", "customrecord_subpo"),
        ("customs-declarations", "customrecord_customs"),
    ],
)
def test_pull_page_is_read_only_and_exact(sync_api, kind, record_type):
    client, headers, context, calls = sync_api
    response = client.post(f"/api/ns/sync/{kind}/pull", headers=headers, json={"offset": 20})
    assert response.status_code == 200
    data = response.json()
    assert data["rows"][0]["record"]["amount"] == "123.4500"
    assert data["count"] == 1 and data["nextOffset"] == 40
    assert calls[0][1] == record_type
    assert calls[0][3]["query_params"] == {"limit": 20, "offset": 20}
    assert context.ns.writes == []


def test_auth_validation_and_configuration(sync_api):
    client, headers, context, calls = sync_api
    path = "/api/ns/sync/purchase-orders/pull"
    assert client.post(path, json={}).status_code == 401
    for body in [
        {"limit": 21},
        {"offset": -1},
        {"offset": True},
        {"offset": 1},
        {"offset": 20000},
        {"url": "https://invalid"},
    ]:
        assert client.post(path, headers=headers, json=body).status_code == 400
    assert client.post("/api/ns/sync/unknown/pull", headers=headers, json={}).status_code == 400
    assert calls == []
    context.settings.record_types = []
    assert client.post(path, headers=headers, json={}).status_code == 503
    assert not client.get("/api/ns/sync/sources", headers=headers).json()["sources"][0]["allowed"]
    assert calls == []


@pytest.mark.parametrize(
    "data",
    [
        None,
        {"items": []},
        {"items": [], "hasMore": True},
        {"items": [{"id": "1"}, {"id": "1"}], "hasMore": False},
    ],
)
def test_invalid_upstream_pages_fail(sync_api, data):
    client, headers, context, _ = sync_api

    def request(method, record_type, record_id=None, **kwargs):
        return {"data": {"id": record_id} if record_id else data}

    context.ns.request = request
    response = client.post("/api/ns/sync/purchase-orders/pull", headers=headers, json={})
    assert response.status_code == 502
    assert "rows" not in response.json()


def test_detail_failure_does_not_report_partial_success(sync_api):
    client, headers, context, _ = sync_api

    def request(method, record_type, record_id=None, **kwargs):
        if record_id:
            raise ApiError(502, "NS 读取失败")
        return {"data": {"items": [{"id": "1"}], "hasMore": False}}

    context.ns.request = request
    assert client.post("/api/ns/sync/purchase-orders/pull", headers=headers, json={}).status_code == 502


def test_empty_page_and_unconfigured_mapping(sync_api):
    client, headers, context, _ = sync_api
    context.ns.request = lambda *args, **kwargs: {"data": {"items": [], "hasMore": False}}
    result = client.post("/api/ns/sync/purchase-orders/pull", headers=headers, json={}).json()
    assert result["count"] == 0 and result["nextOffset"] is None
    context.settings.pl_lookup = {}
    assert client.post("/api/ns/sync/sub-purchase-orders/pull", headers=headers, json={}).status_code == 503


@pytest.mark.parametrize(
    "kind,field",
    [
        ("purchase-orders", "createdDate"),
        ("sub-purchase-orders", "created"),
        ("customs-declarations", "created"),
    ],
)
@pytest.mark.parametrize(
    "start,end,exclusive_end",
    [
        ("2024-02-29", "2024-02-29", "2024-03-01"),
        ("2026-09-01", "2026-09-30", "2026-10-01"),
        ("2026-12-31", "2026-12-31", "2027-01-01"),
    ],
)
def test_created_date_range_reaches_ns_on_every_page(sync_api, kind, field, start, end, exclusive_end):
    client, headers, context, calls = sync_api
    expected = f'{field} ON_OR_AFTER "{start}" AND {field} BEFORE "{exclusive_end}"'
    for offset in (0, 20):
        calls.clear()
        response = client.post(
            f"/api/ns/sync/{kind}/pull",
            headers=headers,
            json={"startDate": start, "endDate": end, "offset": offset},
        )
        assert response.status_code == 200
        assert calls[0][3]["query_params"] == {"q": expected, "limit": 20, "offset": offset}
        assert "query_params" not in calls[1][3]
        assert response.json()["dateRange"] == {"startDate": start, "endDate": end, "label": "创建日期"}
        assert context.ns.writes == []


@pytest.mark.parametrize(
    "body",
    [
        {"startDate": "2026-09-01"},
        {"endDate": "2026-09-01"},
        {"startDate": "2026-09-02", "endDate": "2026-09-01"},
        {"startDate": "2026-02-29", "endDate": "2026-03-01"},
        {"startDate": "20260901", "endDate": "20260901"},
        {"startDate": "1899-01-01", "endDate": "2101-01-01"},
        {"startDate": None, "endDate": None},
        {"startDate": 1, "endDate": 1},
        {"startDate": "2026-09-01", "endDate": "2026-09-01", "dateField": "created OR id"},
    ],
)
def test_invalid_dates_rejected_before_ns_request(sync_api, body):
    client, headers, _, calls = sync_api
    response = client.post("/api/ns/sync/customs-declarations/pull", headers=headers, json=body)
    assert response.status_code == 400
    assert calls == []


@pytest.mark.parametrize(
    "start,end,message",
    [
        ("2026-09-01", "", "请同时填写开始日期和结束日期"),
        ("2026-09-02", "2026-09-01", "开始日期不能晚于结束日期"),
        ("2026-02-30", "2026-03-01", "请填写有效日期，格式为 YYYY-MM-DD"),
    ],
)
def test_date_validation_returns_safe_chinese_message(sync_api, start, end, message):
    client, headers, _, calls = sync_api
    response = client.post(
        "/api/ns/sync/customs-declarations/pull", headers=headers, json={"startDate": start, "endDate": end}
    )
    assert response.status_code == 400
    assert response.json()["error"] == message
    assert calls == []


@pytest.mark.parametrize(
    "date_format,start,end",
    [
        ("YYYY-MM-DD", "2026-12-30", "2027-01-01"),
        ("M/D/YYYY", "12/30/2026", "1/1/2027"),
        ("D/M/YYYY", "30/12/2026", "1/1/2027"),
    ],
)
def test_configured_date_format_reaches_ns(sync_api, date_format, start, end):
    client, headers, context, calls = sync_api
    context.settings.sync_date_format = load_settings(
        {"NETSUITE_SYNC_DATE_FORMAT": date_format}
    ).sync_date_format
    for offset in (0, 20):
        calls.clear()
        response = client.post(
            "/api/ns/sync/customs-declarations/pull",
            headers=headers,
            json={"startDate": "2026-12-30", "endDate": "2026-12-31", "offset": offset},
        )
        assert response.status_code == 200
        assert calls[0][3]["query_params"]["q"] == (
            f'created ON_OR_AFTER "{start}" AND created BEFORE "{end}"'
        )
        assert response.json()["dateRange"]["endDate"] == "2026-12-31"


def test_invalid_date_format_configuration_is_rejected():
    assert load_settings({}).sync_date_format == "YYYY-MM-DD"
    with pytest.raises(ValueError, match="NETSUITE_SYNC_DATE_FORMAT"):
        load_settings({"NETSUITE_SYNC_DATE_FORMAT": "MM-DD-YYYY"})


def test_date_filter_failure_does_not_retry_without_filter(sync_api):
    client, headers, context, calls = sync_api

    def request(method, record_type, record_id=None, **kwargs):
        calls.append(kwargs)
        raise ApiError(502, "NS 请求未成功（HTTP 400）；请核对 NS 权限和字段")

    context.ns.request = request
    response = client.post(
        "/api/ns/sync/customs-declarations/pull",
        headers=headers,
        json={"startDate": "2026-09-01", "endDate": "2026-09-16"},
    )
    assert response.status_code == 502
    assert len(calls) == 1
    assert 'created ON_OR_AFTER "2026-09-01"' in calls[0]["query_params"]["q"]
    assert "rows" not in response.json()
