"""已入库账套筛选：离线名称、不同账套隔离、列表与统计一致。"""

from decimal import Decimal

from backend.modules.invoice.entity import headers
from backend.modules.sync.dao import lemon_binding_dao as bindings
from backend.tests.sync.test_lemon_invoices import BASE, OWNER, body, invoice
from backend.tests.sync.test_lemon_invoices import setup as setup
from sqlalchemy import update


def test_account_filter_options_and_totals(setup, monkeypatch):
    client = setup.client
    assert client.get(f"{BASE}/invoices/accounts").json() == {"items": []}
    assert client.post(f"{BASE}/invoices/pull-save", json=body()).status_code == 200
    setup.upstream.rows = [invoice(InvoiceId=2, Number="26000000000000000002")]
    assert client.post(f"{BASE}/invoices/pull-save", json=body()).status_code == 200
    setup.accounts.select(OWNER, "8")
    setup.upstream.rows = [invoice(InvoiceId=3, Number="26000000000000000003")]
    assert client.post(f"{BASE}/invoices/pull-save", json=body(asid="8")).status_code == 200

    def no_external_call(*args):
        raise AssertionError("筛选账套不能调用上游")

    monkeypatch.setattr(setup.upstream, "user_token", no_external_call)
    with setup.engine.begin() as connection:
        bindings.transition(connection, setup.accounts.binding._scope(OWNER), ("bound",), "unbound")
    options = client.get(f"{BASE}/invoices/accounts").json()["items"]
    assert len(options) == 2
    account = next(row["value"] for row in options if row["label"].startswith("测试账套"))
    params = {"account": account, "page_size": 1, "page": 2}
    page = client.get("/api/invoices", params=params).json()
    assert page["total"] == 2 and len(page["rows"]) == 1
    assert page["rows"][0]["number"] != "26000000000000000003"
    totals = client.get("/api/matching/invoice-totals", params={"account": account}).json()["amounts"][0]
    assert totals["count"] == 2
    assert Decimal(totals["gross"]) == Decimal(page["amounts"][0]["gross"]) == Decimal("226")
    assert Decimal(totals["pendingAmount"]) == Decimal("226")
    assert Decimal(totals["tax"]) == Decimal("26")
    assert Decimal(totals["reviewAmount"]) == 0
    assert client.get("/api/invoices").json()["total"] == 3
    for filters in (
        {"account": "missing"},
        {"account": account, "q": "26000000000000000003"},
        {"account": account, "status": "void"},
        {"account": account, "date_from": "2026-11-01"},
    ):
        assert client.get("/api/invoices", params=filters).json()["total"] == 0
        assert client.get("/api/matching/invoice-totals", params=filters).json()["amounts"] == []
    assert client.get(f"{BASE}/invoices/accounts").json()["items"] == options


def test_excel_historical_options_and_validation(setup):
    client = setup.client
    client.post(f"{BASE}/invoices/pull-save", json=body())
    with setup.engine.begin() as connection:
        connection.execute(update(headers).values(lemon_account="lemon"))
    assert client.get(f"{BASE}/invoices/accounts").json()["items"] == [
        {"value": "lemon", "label": "Excel 导入（账套未对齐）"}
    ]
    with setup.engine.begin() as connection:
        connection.execute(update(headers).values(lemon_account="historical-account"))
    option = client.get(f"{BASE}/invoices/accounts").json()["items"][0]
    assert option["value"] == "historical-account" and "名称未记录" in option["label"]
    for path in ("/api/invoices", "/api/matching/invoice-totals"):
        assert client.get(path, params={"account": "x" * 101}).status_code == 400
    client.cookies.clear()
    assert client.get(f"{BASE}/invoices/accounts").status_code == 401
