"""上游失败必须可定位阶段，同时不输出授权信息或业务正文。"""

import logging

import httpx
import pytest
from backend.core.errors import ApiError
from backend.tests.sync.test_lemon_protocol import client


@pytest.mark.parametrize("operation", ["user_token", "accounts", "account_permissions", "invoices"])
@pytest.mark.parametrize("failure", ["status", "timeout", "connect", "json", "business", "data"])
def test_stage_and_safe_failure_details(caplog, operation, failure):
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private-exception", request=request)
        if failure == "connect":
            raise httpx.ConnectError("private-exception", request=request)
        if failure == "business":
            return httpx.Response(200, json={"State": 2000, "SubState": 12, "Msg": "private-message"})
        if failure == "data":
            return httpx.Response(200, json={"State": 1000, "Data": "private-data"})
        return httpx.Response(403 if failure == "status" else 200, text="private-response")

    upstream = client(handler)
    try:
        with caplog.at_level(logging.ERROR, logger="ns_api.lemon"), pytest.raises(ApiError) as error:
            if operation == "user_token":
                upstream.user_token("13800000001")
            elif operation == "accounts":
                upstream.accounts("private-token")
            elif operation == "account_permissions":
                upstream.account_service_ids("private-token", "private-account")
            else:
                upstream.invoices("private-token", "private-account", "2026-10-01", "2026-10-16")
    finally:
        upstream.close()
    assert len(calls) == 1  # 诊断不自动重试或切换接口。
    assert error.value.status == 502
    records = [record for record in caplog.records if record.name == "ns_api.lemon"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert f"operation={operation}" in message and "duration_ms=" in message
    assert "page=1" in message if operation == "invoices" else "page=None" in message
    combined = message + str(error.value)
    for secret in ("private-", "global-secret", "13800000001", "https://", "2026-10-01"):
        assert secret not in combined
    if failure == "status":
        assert "upstream_status=403" in message and "HTTP 403" in str(error.value)
    elif failure == "timeout":
        assert "type=timeout" in message and "超时" in str(error.value)
    elif failure == "connect":
        assert "type=ConnectError" in message
    elif failure == "json":
        assert "upstream_status=200" in message and "有效 JSON" in str(error.value)
    elif failure == "business":
        assert "state=2000 substate=12" in message
    else:
        assert "type=invalid_data" in message


def test_untrusted_business_codes_are_not_logged(caplog):
    upstream = client(
        lambda request: httpx.Response(
            200,
            json={
                "State": "private-state",
                "SubState": "private-substate",
                "Msg": "private-message",
            },
        )
    )
    try:
        with caplog.at_level(logging.ERROR, logger="ns_api.lemon"), pytest.raises(ApiError) as error:
            upstream.accounts("private-token")
    finally:
        upstream.close()
    assert "private-" not in caplog.text + str(error.value)
