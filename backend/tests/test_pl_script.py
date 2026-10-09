"""共用NS规则入口：真实HTTP适配用MockTransport，禁止网络及NS写入。"""

import copy
import time

import httpx
import pytest
from backend.app import create_app
from backend.core.config import Settings, load_settings
from backend.core.errors import ApiError
from backend.integrations.netsuite.client import NetSuite
from backend.modules.business.dto import PlScriptQuery
from backend.modules.business.pl_script_service import PlScriptService
from fastapi.testclient import TestClient
from pydantic import ValidationError


def result(version=1):
    data = {
        "contractVersion": version,
        "complete": True,
        "source": "netsuite-script",
        "account": "TEST_SB1",
        "requestId": "query-1",
        "query": PlScriptQuery(pl="PL001").model_dump(),
        "readStartedAt": "2026-09-16T01:00:00Z",
        "readCompletedAt": "2026-09-16T01:00:01Z",
        "elapsedMs": 1000,
        "monthDateLabel": "申报日期",
        "counts": {"customs": 1, "purchase": 1, "declarations": 0, "groups": 1},
        "declarations": [],
        "groups": [
            {
                "id": "head:1",
                "title": "CD000001",
                "customsCount": 1,
                "purchaseCount": 1,
                "warnings": ["来源币种未确认"],
                "rows": [
                    {
                        "id": "customs:0",
                        "side": "customs",
                        "cells": [""] * 13 + ["2.00", "119.99"],
                        "note": "",
                    },
                    {
                        "id": "purchase:0",
                        "side": "purchase",
                        "cells": [""] * 13 + ["2.00", "119.99"],
                        "note": "",
                    },
                ],
            }
        ],
    }
    if version == 2:
        customs, purchase = data["groups"][0]["rows"]
        customs["cells"].extend(["0.64", "US Dollar"])
        purchase["cells"].extend(["", ""])
    return data


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"month": "2026-13"},
        {"month": "1899-12"},
        {"createdFrom": "2026-09-01"},
        {"createdFrom": "2026-02-30", "createdTo": "2026-03-01"},
        {"createdFrom": "2026-09-02", "createdTo": "2026-09-01"},
        {"pl": "A\x00B"},
        {"pl": "X" * 101},
        {"pl": "PL1", "showIncomplete": "false"},
        {"pl": "PL1", "script": "other"},
        {"type": "unknown", "pl": "1"},
    ],
)
def test_invalid_scope(body):
    with pytest.raises(ValidationError):
        PlScriptQuery.model_validate(body)


@pytest.mark.parametrize(
    "body",
    [
        {"pl": " PL001 "},
        {"month": "2026-09"},
        {"type": "customsRecord", "pl": "CD000001", "showIncomplete": False},
        {"type": "declaration", "pl": "真实报关编号-1", "month": "2026-09"},
        {"createdFrom": "2024-02-29", "createdTo": "2024-03-01"},
    ],
)
def test_valid_scope(body):
    assert PlScriptQuery.model_validate(body)


def client_for(handler, **settings):
    ns = NetSuite(
        Settings(
            account="test-sb1",
            scope=["rest_webservices", "restlets"],
            pl_restlet_script="123",
            pl_restlet_deploy="1",
            **settings,
        ),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    ns._cached = ("private-token", time.monotonic() + 300)
    return ns


@pytest.mark.parametrize("version", [1, 2])
def test_transport_and_result_preserve_decimal_order_and_same_export(version):
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "POST"
        assert request.url.host == "test-sb1.restlets.api.netsuite.com"
        assert dict(request.url.params) == {"script": "123", "deploy": "1"}
        assert request.headers["authorization"] == "Bearer private-token"
        return httpx.Response(200, json=result(version))

    ns = client_for(handle)
    actual = PlScriptService(ns).query(PlScriptQuery(pl="PL001"))
    assert len(calls) == 1
    assert actual.contractVersion == version
    assert all(len(row.cells) == (15 if version == 1 else 17) for row in actual.groups[0].rows)
    assert [row.side for row in actual.groups[0].rows] == ["customs", "purchase"]
    assert actual.groups[0].rows[1].cells[14] == "119.99"
    assert "download" not in actual.model_dump()
    assert "private-token" not in actual.model_dump_json()


def test_v2_customs_price_currency_and_multiple_rows_preserve_ns_strings():
    data = result(2)
    customs, purchase = data["groups"][0]["rows"]
    customs["cells"][15:] = ["0.00", "US Dollar"]
    customs["missingCells"] = [15, 16]
    another_customs = copy.deepcopy(customs)
    another_customs.update(id="customs:1", missingCells=[])
    another_customs["cells"][15:] = ["0.64", "人民币"]
    another_purchase = copy.deepcopy(purchase)
    another_purchase.update(id="purchase:1")
    data["groups"][0]["rows"].extend([another_customs, another_purchase])
    data["groups"][0].update(customsCount=2, purchaseCount=2)
    data["counts"].update(customs=2, purchase=2)
    ns = client_for(lambda request: httpx.Response(200, json=data))

    actual = PlScriptService(ns).query(PlScriptQuery(pl="PL001"))

    assert actual.contractVersion == 2
    assert actual.counts.customs == actual.counts.purchase == 2
    rows = actual.groups[0].rows
    assert [row.side for row in rows] == ["customs", "purchase", "customs", "purchase"]
    assert [row.cells for row in rows] == [row["cells"] for row in data["groups"][0]["rows"]]
    assert rows[0].cells[13:17] == ["2.00", "119.99", "0.00", "US Dollar"]
    assert rows[2].cells[13:17] == ["2.00", "119.99", "0.64", "人民币"]
    assert all(15 not in row.missingCells and 16 not in row.missingCells for row in rows)


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("column_count", [14, 15, 16, 17, 18])
def test_each_row_column_count_must_match_contract_version(version, column_count):
    expected = 15 if version == 1 else 17
    data = result(version)
    # 保留首行合法，验证不会仅检查第一行或按最长行补齐。
    data["groups"][0]["rows"][1]["cells"] = [""] * column_count
    ns = client_for(lambda request: httpx.Response(200, json=data))
    if column_count == expected:
        assert PlScriptService(ns).query(PlScriptQuery(pl="PL001")).contractVersion == version
    else:
        with pytest.raises(ApiError, match="契约或完整性校验失败"):
            PlScriptService(ns).query(PlScriptQuery(pl="PL001"))


@pytest.mark.parametrize("version", [0, 4, "2", True, 2.0, None])
def test_unknown_or_non_integer_contract_version_rejected(version):
    data = result(2)
    data["contractVersion"] = version
    ns = client_for(lambda request: httpx.Response(200, json=data))
    with pytest.raises(ApiError, match="契约或完整性校验失败"):
        PlScriptService(ns).query(PlScriptQuery(pl="PL001"))


@pytest.mark.parametrize("index", [15, 16])
@pytest.mark.parametrize("value", [0, 0.0, None, False, {"text": "US Dollar"}])
def test_v2_customs_extra_columns_require_strings(index, value):
    data = result(2)
    data["groups"][0]["rows"][0]["cells"][index] = value
    ns = client_for(lambda request: httpx.Response(200, json=data))
    with pytest.raises(ApiError, match="契约或完整性校验失败"):
        PlScriptService(ns).query(PlScriptQuery(pl="PL001"))


@pytest.mark.parametrize("extra_cells", [["0.00", ""], ["", "US Dollar"], [" ", ""]])
def test_v2_purchase_does_not_claim_customs_price_or_currency(extra_cells):
    data = result(2)
    data["groups"][0]["rows"][1]["cells"][15:] = extra_cells
    ns = client_for(lambda request: httpx.Response(200, json=data))
    with pytest.raises(ApiError, match="契约或完整性校验失败"):
        PlScriptService(ns).query(PlScriptQuery(pl="PL001"))


@pytest.mark.parametrize("version", [1, 2])
def test_empty_result_preserves_contract_version(version):
    data = result(version)
    data["groups"] = []
    data["counts"] = {"customs": 0, "purchase": 0, "declarations": 0, "groups": 0}
    ns = client_for(lambda request: httpx.Response(200, json=data))
    actual = PlScriptService(ns).query(PlScriptQuery(pl="PL001"))
    assert actual.contractVersion == version
    assert actual.groups == []


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(account="other"),
        lambda d: d.update(contractVersion=4),
        lambda d: d["query"].update(pl="PL002"),
        lambda d: d["counts"].update(purchase=2),
        lambda d: d["groups"][0]["rows"].pop(),
        lambda d: d["groups"][0]["rows"][1]["cells"].__setitem__(14, 119.99),
        lambda d: d.update(download={"contentBase64": "unexpected"}),
        lambda d: d.update(complete=False),
    ],
)
def test_incomplete_wrong_account_or_contract_rejected(mutation, version):
    data = result(version)
    mutation(data)
    ns = client_for(lambda request: httpx.Response(200, json=data))
    with pytest.raises(ApiError):
        PlScriptService(ns).query(PlScriptQuery(pl="PL001"))


@pytest.mark.parametrize("version", [1, 2])
def test_missing_fields_respect_source_and_preserve_zero_and_ns_notes(version):
    data = result(version)
    customs, purchase = data["groups"][0]["rows"]
    customs["cells"] = [
        "CD1",
        "2026-09-16",
        "PL001",
        "",
        "",
        "",
        "",
        "",
        "公司",
        "商品",
        "",
        "0",
        "件",
        "",
        "",
    ]
    purchase["cells"] = [
        "",
        "",
        "",
        "",
        "未填写",
        "PO1",
        "",
        "  ",
        "",
        "商品",
        "",
        "0",
        "件",
        "待确认",
        "0.00",
    ]
    purchase["note"] = "未能唯一关联，待核对"
    if version == 2:
        customs["cells"].extend(["", ""])
        purchase["cells"].extend(["", ""])
    ns = client_for(lambda request: httpx.Response(200, json=data))
    actual = PlScriptService(ns).query(PlScriptQuery(pl="PL001"))
    assert actual.groups[0].rows[0].missingCells == []
    assert actual.groups[0].rows[1].missingCells == [4, 7, 13]
    assert actual.groups[0].rows[1].note == purchase["note"]
    assert actual.groups[0].warnings == data["groups"][0]["warnings"]
    assert "download" not in actual.model_dump()


@pytest.mark.parametrize("status", [302, 401, 403, 429, 500])
def test_no_redirect_no_retry_no_platform_error_exposure(status):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            status, headers={"location": "https://other.invalid"}, text="secret platform error"
        )

    ns = client_for(handle)
    with pytest.raises(ApiError) as caught:
        ns.pl_script_query({"pl": "PL001"})
    assert len(calls) == 1 and "secret" not in caught.value.message
    if status == 401:
        assert ns._cached is None


def test_missing_configuration_does_not_call_ns():
    ns = NetSuite(Settings())
    with pytest.raises(ApiError, match="尚未配置"):
        ns.pl_script_query({"pl": "PL001"})
    ns.settings.pl_restlet_script = "1"
    ns.settings.pl_restlet_deploy = "1"
    with pytest.raises(ApiError, match="restlets"):
        ns.pl_script_query({"pl": "PL001"})


def test_config_rejects_url_and_query_injection(env):
    with pytest.raises(ValueError):
        load_settings({**env, "NETSUITE_PL_RESTLET_SCRIPT": "1&deploy=other"})


def test_transport_rejects_oversized_or_non_json_response():
    for response in (
        httpx.Response(200, content=b"x" * (8 * 1024 * 1024 + 1)),
        httpx.Response(200, text="<html>登录页</html>"),
    ):
        ns = client_for(lambda request: response)
        with pytest.raises(ApiError):
            ns.pl_script_query({"pl": "PL001"})


def test_timeout_does_not_retry():
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("private detail", request=request)

    ns = client_for(handle)
    with pytest.raises(ApiError, match="前一只读请求可能仍在执行"):
        ns.pl_script_query({"pl": "PL001"})
    assert len(calls) == 1


@pytest.mark.parametrize("version", [1, 2])
def test_endpoint_authentication_and_validation_before_ns(context, version):
    context.settings.account = "test-sb1"
    calls = []

    def query(body):
        calls.append(copy.deepcopy(body))
        return result(version)

    context.ns.pl_script_query = query
    with TestClient(create_app(context.settings, context.ns, context.engine)) as client:
        path = "/api/ns/pl-script-comparison"
        assert client.post(path, json={"pl": "PL001"}).status_code == 401
        headers = {"Authorization": f"Bearer {context.settings.service_key}"}
        invalid = client.post(path, json={}, headers=headers)
        assert invalid.status_code == 400
        assert "至少填写一项" in invalid.json()["error"]
        assert calls == []
        response = client.post(path, json={"pl": "PL001"}, headers=headers)
        assert response.status_code == 200
        assert response.json()["contractVersion"] == version
        assert len(response.json()["groups"][0]["rows"][0]["cells"]) == (15 if version == 1 else 17)
        assert calls == [PlScriptQuery(pl="PL001").model_dump()]
        assert context.ns.writes == []
