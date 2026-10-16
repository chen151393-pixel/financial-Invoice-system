"""原始追溯可选：只对明确的结构不可见降级，损坏来源和连接失败仍拒绝。"""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from backend.core.errors import ApiError
from backend.modules.source.service.relation_reader import RAW_FIELDS, read_originals
from backend.tests.test_source_storage import ACCOUNT, config


def client(response):
    return SimpleNamespace(
        settings=SimpleNamespace(
            account=ACCOUNT, pl_lookup=config(), finance_source_script="482", finance_source_deploy="1"
        ),
        finance_source_query=lambda ids: deepcopy(response),
    )


def unavailable(code="RAW_SUBLIST_UNAVAILABLE", **overrides):
    return {
        "contractVersion": 1,
        "account": ACCOUNT,
        "complete": False,
        "error": {"code": code},
        **overrides,
    }


def success(ids=("870",)):
    return {
        "contractVersion": 1,
        "account": ACCOUNT,
        "complete": True,
        "declarations": [
            {
                "id": identity,
                "recordNumber": f"CD{identity}",
                "rows": [{**dict.fromkeys(RAW_FIELDS, ""), "id": identity, "declarationId": identity}],
            }
            for identity in ids
        ],
    }


@pytest.mark.parametrize("code", ["RAW_SUBLIST_UNAVAILABLE", "RAW_FIELDS_UNAVAILABLE"])
def test_only_structural_unavailability_is_optional(code):
    data, issue = read_originals(client(unavailable(code)), {"870": {"name": "CD870"}})
    assert data == {} and "精确追溯未完成" in issue


@pytest.mark.parametrize(
    "response",
    [
        unavailable(account="other"),
        unavailable(contractVersion=2),
        unavailable(contractVersion=True),
        unavailable(declarations=[]),
        unavailable(complete="false"),
        unavailable(error=[]),
        unavailable(error={"code": []}),
        unavailable("SOURCE_READ_FAILED"),
        unavailable("QUERY_LIMIT"),
        unavailable("INVALID_SOURCE_CONFIG"),
        unavailable("UNKNOWN"),
        {"mode": "diagnose", "complete": False, "contractVersion": 1, "account": ACCOUNT},
        None,
    ],
)
def test_invalid_or_non_optional_response_still_fails(response):
    with pytest.raises(ApiError):
        read_originals(client(response), {"870": {"name": "CD870"}})


@pytest.mark.parametrize("message", ["NS认证失败", "NS连接超时"])
def test_connection_and_auth_errors_are_not_swallowed(message):
    ns = client(None)

    def fail(ids):
        raise ApiError(502, message)

    ns.finance_source_query = fail
    with pytest.raises(ApiError, match=message):
        read_originals(ns, {"870": {"name": "CD870"}})


@pytest.mark.parametrize(
    "case", ["missing_field", "wrong_header", "duplicate", "wrong_number", "missing_document"]
)
def test_success_payload_must_still_be_complete(case):
    response = success()
    declaration = response["declarations"][0]
    if case == "missing_field":
        del declaration["rows"][0]["packingId"]
    elif case == "wrong_header":
        declaration["rows"][0]["declarationId"] = "999"
    elif case == "duplicate":
        declaration["rows"] *= 2
    elif case == "wrong_number":
        declaration["recordNumber"] = "OTHER"
    else:
        response["declarations"] = []
    with pytest.raises(ApiError):
        read_originals(client(response), {"870": {"name": "CD870"}})


def test_later_unavailable_batch_discards_earlier_raw_rows():
    ns = client(None)
    ids = [str(i) for i in range(1, 22)]
    calls = []

    def query(batch):
        calls.append(batch)
        return success(batch) if len(calls) == 1 else unavailable()

    ns.finance_source_query = query
    data, issue = read_originals(ns, {identity: {"name": f"CD{identity}"} for identity in ids})
    assert list(map(len, calls)) == [20, 1]
    assert data == {} and "精确追溯未完成" in issue
