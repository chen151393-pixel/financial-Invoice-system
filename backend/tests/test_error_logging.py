"""日志覆盖请求边界与 NS 失败，且不得泄露敏感内容。"""

import logging
import time

import httpx
import pytest
from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.core.middleware import RequestGuard, register_error_handlers
from backend.integrations.netsuite.client import NetSuite
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_successful_api_request_is_logged_without_private_data(caplog):
    app = FastAPI()
    app.add_middleware(RequestGuard, secure=False)

    @app.post("/api/example/{record_id}")
    def example(record_id: str):
        return {"ok": True}

    with TestClient(app) as client, caplog.at_level(logging.INFO, logger="ns_api"):
        response = client.post(
            "/api/example/private-id?query=private-query",
            json={"secret": "private-body"},
            headers={"Authorization": "Bearer private-token"},
        )
    assert response.status_code == 200
    records = [r for r in caplog.records if r.name == "ns_api"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "request_completed method=POST route=/api/example/{record_id} status=200" in message
    assert "duration_ms=" in message
    assert "private-" not in message


def test_startup_enables_application_info_logs(monkeypatch):
    from backend import __main__ as entry

    calls = []
    monkeypatch.setattr(entry, "load_settings", lambda: load_settings({}))
    monkeypatch.setattr(entry.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    entry.main()
    config = calls[0]["log_config"]
    assert config["loggers"]["ns_api"] == {"handlers": ["default"], "level": "INFO", "propagate": False}
    assert "default" in config["handlers"]
    assert calls[0]["access_log"] is False


@pytest.mark.parametrize(
    "kind,status", [("api", 502), ("unexpected", 500), ("validation", 400), ("guard", 400), ("missing", 404)]
)
def test_request_failure_log(caplog, kind, status):
    app = FastAPI()
    app.add_middleware(RequestGuard, secure=False)
    register_error_handlers(app)

    @app.post("/api/example/{record_id}")
    def example(record_id: str, count: int = 1):
        if kind == "api":
            raise ApiError(502, "private-error")
        if kind == "unexpected":
            raise RuntimeError("private-error")
        return {"ok": True}

    with TestClient(app) as client, caplog.at_level(logging.WARNING, logger="ns_api"):
        response = client.post(
            "/api/missing/private-id" if kind == "missing" else "/api/example/private-id",
            params={"count": "private-query" if kind == "validation" else "1"},
            content="private-body" if kind == "guard" else '{"secret":"private-body"}',
            headers={"Content-Type": "application/json", "Authorization": "Bearer private-token"},
        )
    assert response.status_code == status
    records = [r for r in caplog.records if r.name == "ns_api"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert f"status={status}" in message
    assert "method=POST" in message and "duration_ms=" in message
    assert "private-" not in message
    if kind in ("api", "unexpected", "validation"):
        assert "route=/api/example/{record_id}" in message
    if kind == "unexpected":
        assert "type=RuntimeError" in message


@pytest.mark.parametrize("operation", ["record", "token", "restlet"])
@pytest.mark.parametrize("failure", ["timeout", "connect", "status", "json"])
def test_ns_failure_log(env, tmp_path, monkeypatch, caplog, operation, failure):
    key = tmp_path / "test.pem"
    key.write_text("private-key", encoding="utf-8")
    settings = load_settings(
        {
            **env,
            "NETSUITE_CLIENT_ID": "test",
            "NETSUITE_CERTIFICATE_ID": "test",
            "NETSUITE_PRIVATE_KEY_PATH": str(key),
        }
    )
    settings.scope = ["rest_webservices", "restlets"]
    settings.pl_restlet_script = "123"
    settings.pl_restlet_deploy = "1"
    monkeypatch.setattr("backend.integrations.netsuite.client.assertion", lambda *_: "private-assertion")
    calls = []

    def handle(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private-exception", request=request)
        if failure == "connect":
            raise httpx.ConnectError("private-exception", request=request)
        return httpx.Response(403 if failure == "status" else 200, text="private-response")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        ns = NetSuite(settings, client)
        if operation != "token":
            ns._cached = ("private-token", time.monotonic() + 300)
        with caplog.at_level(logging.ERROR, logger="ns_api.netsuite"), pytest.raises(ApiError):
            if operation == "record":
                ns.request("PATCH", "vendorBill", "1", {"memo": "private-payload"})
            elif operation == "token":
                ns.token()
            else:
                ns.pl_script_query({"pl": "private-payload"})
    assert len(calls) == 1
    records = [r for r in caplog.records if r.name == "ns_api.netsuite"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert f"operation={operation}" in message and "duration_ms=" in message
    assert "private-" not in message
    if failure == "timeout":
        assert "type=ReadTimeout" in message
    elif failure == "connect":
        assert "type=ConnectError" in message
    elif failure == "status":
        assert "upstream_status=403" in message
    else:
        assert "upstream_status=200" in message
