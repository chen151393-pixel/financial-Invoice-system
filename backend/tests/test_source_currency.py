"""母采购币种：使用母单显式币种信息，不依赖独立币种表权限或默认币种。"""

import json
from decimal import Decimal

import httpx
import pytest
from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.integrations.netsuite.client import NetSuite
from backend.modules.source.policy.currency_policy import resolve
from backend.modules.source.service.parent_order_reader import read_parent_orders
from backend.modules.source.service.storage_service import StorageService
from backend.tests.test_source_optional_sync import source as source  # 共用完整 NS 读取夹具
from backend.tests.test_source_storage import ACCOUNT, PARENT, bundle, customs, purchase, rows
from backend.tests.test_source_storage import engine as engine  # 共用隔离库
from backend.tests.test_source_storage import ns as ns  # source 夹具依赖


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("人民币", "CNY"),
        ("人民币元", "CNY"),
        ("美元", "USD"),
        ("欧元", "EUR"),
        ("英镑", "GBP"),
        ("日元", "JPY"),
        ("港币", "HKD"),
        ("澳元", "AUD"),
        ("加拿大元", "CAD"),
        ("新加坡元", "SGD"),
        ("瑞士法郎", "CHF"),
        ("新台币", "TWD"),
        (" cny ", "CNY"),
        ("USD", "USD"),
        (" Japanese Yen ", "JPY"),
    ],
)
def test_explicit_parent_currency_names_and_codes(name, expected):
    assert resolve("100", {"currency": "1", "currencyname": name}) == (expected, "parent_order", None)


@pytest.mark.parametrize(
    "name", ["", "1", "元", "$", "ABC", "RMB", "某币种", "人民币或美元", "美元（待确认）"]
)
def test_unknown_or_ambiguous_names_are_not_guessed(name):
    code, source, issue = resolve("100", {"currency": "1", "currencyname": name})
    assert code is None and source == "unresolved" and "待核实" in issue


@pytest.mark.parametrize(
    "header",
    [
        {"currencysymbol": "USD", "currencyname": "人民币"},
        {"currencysymbol": "$", "currencyname": "美元"},
        {"currencysymbol": "1", "currencyname": "人民币"},
    ],
)
def test_conflicting_or_invalid_explicit_code_does_not_fall_back_to_name(header):
    assert resolve("100", header)[1] == "unresolved"


def test_legacy_codes_and_missing_parent_keep_original_rules():
    assert resolve("100", {"currencysymbol": "USD", "currencyname": "自定义名称"})[0] == "USD"
    assert resolve("100", {"currencysymbol": "CNY", "currencyname": "人民币"})[0] == "CNY"
    assert resolve("", {"currencyname": "人民币"})[1] == "unresolved"
    assert resolve("100", None)[1] == "unresolved"


def test_parent_headers_use_transaction_currency_without_currency_table_or_rest_calls(env):
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "POST"
        assert request.url.path.endswith("/query/v1/suiteql")
        query = json.loads(request.content)["q"]
        assert "BUILTIN.DF(t.currency)" in query
        assert "JOIN currency" not in query and "c.symbol" not in query
        assert "t.type = 'PurchOrd'" in query and "t.id IN (100)" in query
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "100",
                        "tranid": "PO-100",
                        "currency": "1",
                        "currencyname": "人民币",
                        "exchangerate": "1.25",
                    }
                ],
                "hasMore": False,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        ns = NetSuite(load_settings(env), http)
        ns.token = lambda: "test-token"
        parents = read_parent_orders(ns, bundle([purchase(), purchase("201")], [customs()]))
    assert len(calls) == 1
    assert parents["100"]["currency"] == "1"
    assert parents["100"]["exchangerate"] == "1.25"
    assert resolve("100", parents["100"]) == ("CNY", "parent_order", None)


@pytest.mark.parametrize("status", [400, 401, 403, 500])
def test_parent_query_failures_are_not_converted_to_currency_defaults(env, status):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status))) as http:
        ns = NetSuite(load_settings(env), http)
        ns.token = lambda: "test-token"
        with pytest.raises(ApiError):
            read_parent_orders(ns, bundle([purchase()], [customs()]))


def test_named_parent_currency_saves_original_evidence_and_refreshes_dependents(source, engine):
    ns, page, _, _ = source
    original = ns.relation_rows
    header = {key: value for key, value in PARENT.items() if key != "currencysymbol"}
    header["currency"] = "1"

    def read(kind, ids):
        return [dict(header)] if kind == "parent_headers" else original(kind, ids)

    ns.relation_rows = read
    storage = StorageService(ns, engine)
    storage.sync_page("customs-declarations", lambda: page)
    order = rows(engine, "SELECT * FROM source_purchase_orders")[0]
    assert order["currency"] == "CNY" and order["currency_source"] == "parent_order"
    parent = rows(engine, "SELECT * FROM source_parent_orders")[0]
    assert parent["currency_internal_id"] == "1"
    assert Decimal(str(parent["exchange_rate"])) == Decimal("1")
    raw = rows(engine, "SELECT payload FROM source_raw_records WHERE record_type = 'purchaseOrder'")
    value = json.loads(raw[-1]["payload"])
    assert value["currencyname"] == "人民币" and value["currency"] == "1"
    # 相同 ID 的币种信息变化仍会生成新依据版本，而不是从进程缓存沿用人民币。
    header.update(currencyname="美元", currency="2", exchangerate="7.1")
    storage.sync_page("customs-declarations", lambda: page)
    changed = rows(engine, "SELECT * FROM source_purchase_orders")[0]
    assert (
        changed["currency"] == "USD" and changed["currency_raw_record_id"] != order["currency_raw_record_id"]
    )
    assert rows(engine, "SELECT ns_account FROM source_parent_orders")[0]["ns_account"] == ACCOUNT
