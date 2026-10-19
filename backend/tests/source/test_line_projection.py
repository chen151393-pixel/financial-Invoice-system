"""字段投影的 HTTP 协议、身份范围、精度及失败边界。"""

import json
from decimal import Decimal

import httpx
import pytest
from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.integrations.netsuite.client import NetSuite
from backend.modules.source.policy.line_read_policy import line_projection
from backend.modules.source.policy.ns_config import parse_config
from backend.tests.test_source_storage import ns as ns

TYPE = "customrecord_swc_subpo_item"
FIELDS = {
    "custrecord_swc_subpo_item_amountwithtax": False,
    "custrecord_swc_subpo_main": True,
    "isInactive": False,
}


def client(payload, calls, *, status=200):
    def handle(request):
        calls.append(request)
        return httpx.Response(status, content=payload, headers={"content-type": "application/json"})

    result = NetSuite(
        Settings(account="test", record_types=[TYPE]), httpx.Client(transport=httpx.MockTransport(handle))
    )
    result.token = lambda: "test-token"
    return result


def test_batch_protocol_preserves_decimal_references_and_missing_fields():
    calls = []
    ns = client(
        b'{"items":[{"id":"1","f0":900719925474099.123456,"f1":"88","t1":"SUB88","f2":"F"},'
        b'{"id":"2","f2":"T"}],"hasMore":false}',
        calls,
    )
    try:
        result = ns.projected_records(TYPE, ["1", "2"], FIELDS)
    finally:
        ns.close()
    assert len(calls) == 1
    request = calls[0]
    assert request.method == "POST" and request.url.path.endswith("/query/v1/suiteql")
    assert request.headers["prefer"] == "transient"
    query = json.loads(request.content)["q"]
    assert "SELECT *" not in query and "WHERE id IN (1,2) ORDER BY id" in query
    assert "BUILTIN.DF(custrecord_swc_subpo_main)" in query
    assert result["1"][next(iter(FIELDS))] == Decimal("900719925474099.123456")
    assert result["1"]["custrecord_swc_subpo_main"] == {"id": "88", "refName": "SUB88"}
    assert result["1"]["isInactive"] is False and result["2"]["isInactive"] is True
    assert next(iter(FIELDS)) not in result["2"]


@pytest.mark.parametrize(
    "items,more",
    [
        ([], False),
        ([{"id": "1", "f2": "F"}], False),
        ([{"id": "1", "f2": "F"}, {"id": "1", "f2": "F"}], False),
        ([{"id": "1", "f2": "F"}, {"id": "9", "f2": "F"}], False),
        ([{"id": "1"}, {"id": "2", "f2": "F"}], False),
        ([{"id": "1", "f2": "unknown"}, {"id": "2", "f2": "F"}], False),
        ([{"id": "1", "f2": 1}, {"id": "2", "f2": "F"}], False),
        ([{"id": "1", "f2": "F"}, {"id": "2", "f2": "F"}], True),
    ],
)
def test_invalid_or_truncated_rows_are_rejected(items, more):
    calls = []
    ns = client(json.dumps({"items": items, "hasMore": more}).encode(), calls)
    try:
        with pytest.raises(ApiError):
            ns.projected_records(TYPE, ["1", "2"], FIELDS)
    finally:
        ns.close()
    assert len(calls) == 1  # 不降级逐条请求，也不返回部分结果。


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_remote_failure_does_not_fallback_or_retry(status):
    calls = []
    ns = client(b"{}", calls, status=status)
    try:
        with pytest.raises(ApiError):
            ns.projected_records(TYPE, ["1"], FIELDS)
    finally:
        ns.close()
    assert len(calls) == 1


@pytest.mark.parametrize(
    "kind,ids,fields",
    [
        (TYPE, ["1) OR 1=1"], FIELDS),
        (TYPE, ["1", "1"], FIELDS),
        (TYPE, [str(i) for i in range(1, 302)], FIELDS),
        (TYPE, ["1"], {"id,secret": False}),
        (TYPE, ["1"], {"name": "expression"}),
        ("customrecord_unapproved", ["1"], FIELDS),
    ],
)
def test_invalid_projection_rejected_before_network(kind, ids, fields):
    calls = []
    ns = client(b"{}", calls)
    try:
        with pytest.raises(ApiError):
            ns.projected_records(kind, ids, fields)
    finally:
        ns.close()
    assert not calls


def test_line_projection_keeps_rule_fields_and_custom_mapping_compatibility(ns):
    config = parse_config(ns.settings)
    for spec in (config.purchase_line, config.customs_line):
        projection = line_projection(spec)
        assert set(spec.fields.values()) | set(spec.storage_fields.values()) <= projection.keys()
        assert projection[spec.parent] and projection["isInactive"] is False
    fields = line_projection(config.purchase_line)
    assert {"custrecord_swc_subpo_item_mainpo_lineid", "custrecord_swc_subpo_item_solineid"} <= fields.keys()
    config.purchase_line.storage_fields["item_name"] = "custrecord_other_name"
    assert line_projection(config.purchase_line) is None


@pytest.mark.parametrize("duplicate", [False, True])
def test_shared_query_transport_keeps_composite_parent_line_identity(duplicate):
    calls = []
    items = [{"transaction": "1", "id": 0}, {"transaction": "1" if duplicate else "2", "id": 0}]
    ns = client(json.dumps({"items": items, "hasMore": False}).encode(), calls)
    try:
        if duplicate:
            with pytest.raises(ApiError, match="重复"):
                ns.relation_rows("parent_lines", ["1", "2"])
        else:
            assert ns.relation_rows("parent_lines", ["1", "2"]) == items
    finally:
        ns.close()
