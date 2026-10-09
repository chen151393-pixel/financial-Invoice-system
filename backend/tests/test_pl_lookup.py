"""PL 联查边界测试；使用隔离假数据，不调用真实 NS。"""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from backend.app import create_app
from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.integrations.netsuite.client import NetSuite
from backend.modules.business.pl_service import PlLookupService
from fastapi.testclient import TestClient

CONFIG = {
    "pl": {"type": "pl", "number": "name"},
    "purchase": {
        "type": "purchase",
        "pl": "pl",
        "customs": "customs",
        "company": "company",
        "fields": {"purchase": "name"},
    },
    "purchase_line": {"type": "purchase_line", "parent": "parent", "fields": {"amount": "amount"}},
    "customs": {"type": "customs", "fields": {"declaration": "number"}},
    "customs_line": {
        "type": "customs_line",
        "parent": "parent",
        "pl": "pl",
        "company": "company",
        "fields": {"name": "name"},
    },
}


def ref(value):
    return {"id": value}


class LookupNS:
    def __init__(self):
        self.settings = SimpleNamespace(pl_lookup=deepcopy(CONFIG), record_types=list(CONFIG))
        self.calls = []
        self.index = {
            ("pl", "name", "PL001"): ["1"],
            ("purchase", "pl", "1"): ["10", "11"],
            ("purchase_line", "parent", "10"): ["100"],
            ("purchase_line", "parent", "11"): ["101"],
            ("customs_line", "parent", "20"): ["200", "201", "202"],
        }
        self.data = {
            ("purchase", "10"): {"name": "PO1", "pl": ref("1"), "customs": ref("20"), "company": ref("3")},
            ("purchase", "11"): {"name": "PO2", "pl": ref("1"), "customs": ref("20"), "company": ref("3")},
            ("purchase_line", "100"): {"parent": ref("10"), "amount": Decimal("22880.000001")},
            ("purchase_line", "101"): {"parent": ref("11"), "amount": Decimal("1.20")},
            ("customs", "20"): {"number": "CD001"},
            ("customs_line", "200"): {"parent": ref("20"), "pl": ref("1"), "company": ref("3"), "name": "纸"},
            ("customs_line", "201"): {"parent": ref("20"), "pl": ref("9"), "company": ref("3")},
            ("customs_line", "202"): {
                "parent": ref("20"),
                "pl": ref("1"),
                "company": ref("4"),
                "name": "另一公司",
            },
        }

    def validate(self, record_type, record_id):
        assert record_type in self.settings.record_types
        assert record_id.isdigit()

    def filtered_ids(self, record_type, field, value, **kwargs):
        return self.index.get((record_type, field, value), [])

    def request(self, method, record_type, record_id, **kwargs):
        assert method == "GET"
        self.calls.append((record_type, record_id))
        return {"data": self.data[record_type, record_id]}


def test_deduplicates_customs_and_keeps_source_rows():
    ns = LookupNS()
    result = PlLookupService(ns).query("PL001")
    assert result["total"] == 4
    assert ns.calls.count(("customs", "20")) == 1
    assert len([row for row in result["rows"] if row["source"] == "报关"]) == 2
    assert not any(row["id"] == "201" for row in result["rows"])
    assert len({row["group"] for row in result["rows"]}) == 2
    assert next(row for row in result["rows"] if row["id"] == "100")["values"]["amount"] == "22880.000001"


def test_missing_configuration_and_allowlist():
    ns = LookupNS()
    ns.settings.pl_lookup = {}
    assert not PlLookupService(ns).configuration()["ready"]
    with pytest.raises(ApiError):
        PlLookupService(ns).query("PL001")
    ns.settings.pl_lookup = CONFIG
    ns.settings.record_types = ["pl"]
    assert not PlLookupService(ns).configuration()["ready"]
    assert ns.calls == []


def test_missing_reference_retains_purchase_and_failures_propagate():
    ns = LookupNS()
    for key in (("purchase", "10"), ("purchase", "11")):
        ns.data[key].pop("customs")
    result = PlLookupService(ns).query("PL001")
    assert result["total"] == 2
    assert len(result["warnings"]) == 2
    ns.data["purchase_line", "100"] = None
    with pytest.raises(ApiError):
        PlLookupService(ns).query("PL001")


def test_duplicate_pl_is_not_silently_joined():
    ns = LookupNS()
    ns.index["pl", "name", "PL001"] = ["1", "2"]
    with pytest.raises(ApiError, match="多个内部记录"):
        PlLookupService(ns).query("PL001")


def test_paging_and_filter_encoding():
    calls = []

    def respond(request):
        calls.append(dict(request.url.params))
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json={"items": [{"id": str(offset + 1)}], "hasMore": offset == 0})

    ns = NetSuite(
        Settings(account="test", record_types=["pl"]), httpx.Client(transport=httpx.MockTransport(respond))
    )
    ns.token = lambda: "test"
    assert ns.filtered_ids("pl", "name", "PL001") == ["1", "2"]
    assert calls == [
        {"q": 'name IS "PL001"', "limit": "100", "offset": "0"},
        {"q": 'name IS "PL001"', "limit": "100", "offset": "1"},
    ]
    with pytest.raises(ApiError):
        ns.filtered_ids("pl", "name", 'x" OR id EMPTY_NOT')
    ns.close()


def test_endpoint_authentication_and_validation(context):
    app = create_app(context.settings, context.ns, context.engine)
    with TestClient(app) as client:
        assert client.post("/api/ns/pl-lookup", json={"pl": "PL001"}).status_code == 401
        headers = {"Authorization": f"Bearer {context.settings.service_key}"}
        response = client.post("/api/ns/pl-lookup", json={"pl": 'bad"'}, headers=headers)
        assert response.status_code in (400, 422)
        response = client.post("/api/ns/pl-lookup", json={"pl": "PL001"}, headers=headers)
        assert response.status_code == 503


def test_duplicate_page_and_limit_fail_without_partial_data():
    for payload, message in [
        ({"items": [{"id": "1"}], "hasMore": True}, "重复"),
        ({"items": [], "hasMore": True}, "后续数据"),
        ({"items": [{"id": str(i)} for i in range(301)], "hasMore": False}, "过多"),
    ]:
        ns = NetSuite(
            Settings(account="test", record_types=["pl"]),
            httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))),
        )
        ns.token = lambda: "test"
        with pytest.raises(ApiError, match=message):
            ns.filtered_ids("pl", "name", "PL001")
        ns.close()


def test_detail_preserves_decimal_and_denies_unlisted_type():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200, text='{"amount":22880.000000000001}', headers={"content-type": "application/json"}
        )

    ns = NetSuite(
        Settings(account="test", record_types=["pl"]), httpx.Client(transport=httpx.MockTransport(respond))
    )
    ns.token = lambda: "test"
    assert ns.request("GET", "pl", "1", exact_numbers=True)["data"]["amount"] == Decimal("22880.000000000001")
    with pytest.raises(ApiError):
        ns.filtered_ids("other", "name", "PL001")
    assert len(calls) == 1
    ns.close()


def test_result_pagination_does_not_change_total():
    ns = LookupNS()
    ids = [str(1000 + i) for i in range(55)]
    ns.index["purchase_line", "parent", "10"] = ids
    for record_id in ids:
        ns.data["purchase_line", record_id] = {"parent": ref("10"), "amount": Decimal("1.00")}
    service = PlLookupService(ns)
    first, second = service.query("PL001", 1), service.query("PL001", 2)
    assert first["total"] == second["total"] == 58
    assert len(first["rows"]) == 50
    assert len(second["rows"]) == 8
    assert first["hasNext"] and not second["hasNext"]
    assert not (
        {(r["source"], r["id"]) for r in first["rows"]} & {(r["source"], r["id"]) for r in second["rows"]}
    )


def test_foreign_parent_and_ns_failure_do_not_return_success():
    ns = LookupNS()
    ns.data["customs_line", "200"]["parent"] = ref("99")
    with pytest.raises(ApiError, match="所属报关单不一致"):
        PlLookupService(ns).query("PL001")

    def fail(*args, **kwargs):
        raise ApiError(502, "NS 读取失败")

    ns.request = fail
    with pytest.raises(ApiError, match="NS 读取失败"):
        PlLookupService(ns).query("PL001")
