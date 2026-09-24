"""隔离 SQLite 验证只读查询和身份边界；不声明 MySQL 并发验证。"""

import hashlib
from datetime import date
from decimal import Decimal

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.invoice import service as service_module
from backend.modules.invoice.dto import InvoiceQuery
from backend.modules.invoice.service import InvoiceService
from fastapi.testclient import TestClient
from sqlalchemy import JSON, Column, Date, DateTime, Integer, MetaData, Numeric, String, Table, create_engine


@pytest.fixture
def query_service(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'invoices.sqlite'}")
    metadata = MetaData()
    text_fields = "tenant_id invoice_no seller_name seller_tax_no invoice_type_name business_type_name invoice_status invoice_status_raw validation_status currency_code external_system invoice_direction buyer_name buyer_tax_no remark project_name department_name employee_name voucher_reference invoice_code".split()
    head = Table(
        "invoices",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("is_active", Integer),
        Column("invoice_date", Date),
        Column("synced_at", DateTime),
        Column("validation_errors", JSON),
        *[Column(name, String) for name in text_fields],
        *[
            Column(name, Numeric(24, 6))
            for name in ["amount_excluding_tax", "tax_amount", "amount_including_tax"]
        ],
    )
    line = Table(
        "invoice_lines",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("invoice_id", Integer),
        Column("is_active", Integer),
        *[
            Column(name, String)
            for name in "tenant_id line_no item_name specification unit_name tax_rate_raw".split()
        ],
        *[
            Column(name, Numeric(26, 8))
            for name in "quantity unit_price amount_excluding_tax tax_amount amount_including_tax".split()
        ],
    )
    metadata.create_all(engine)
    owner = "service:feishu"
    tenant = hashlib.sha256(owner.encode()).hexdigest()
    common = {
        "tenant_id": tenant,
        "is_active": 1,
        "invoice_direction": "input",
        "invoice_status": "normal",
        "validation_status": "review",
        "external_system": "excel",
        "invoice_date": date(2026, 8, 14),
        "seller_name": "供应商100%",
        "seller_tax_no": "TAX01",
        "invoice_type_name": "数电发票",
        "business_type_name": "采购固定资产",
    }
    with engine.begin() as connection:
        for invoice_id, changes in [
            (1, {}),
            (2, {"currency_code": "USD", "invoice_status": "red_offset"}),
            (3, {"tenant_id": "another"}),
            (4, {"is_active": 0}),
            (5, {"invoice_direction": "output"}),
        ]:
            amount = Decimal("-10.12") if invoice_id == 2 else Decimal("100.123456")
            connection.execute(
                head.insert(),
                {
                    **common,
                    "id": invoice_id,
                    "invoice_no": str(invoice_id).zfill(20),
                    "amount_excluding_tax": amount,
                    "tax_amount": Decimal("0"),
                    "amount_including_tax": amount,
                    **changes,
                },
            )
        connection.execute(
            line.insert(),
            [
                {
                    "id": 1,
                    "invoice_id": 1,
                    "tenant_id": tenant,
                    "is_active": 1,
                    "quantity": Decimal("29.24937028"),
                    "item_name": "商品甲",
                },
                {
                    "id": 2,
                    "invoice_id": 1,
                    "tenant_id": "another",
                    "is_active": 1,
                    "quantity": 1,
                    "item_name": "其他身份明细",
                },
                {
                    "id": 3,
                    "invoice_id": 1,
                    "tenant_id": tenant,
                    "is_active": 0,
                    "quantity": 1,
                    "item_name": "停用明细",
                },
            ],
        )
    monkeypatch.setattr(service_module, "load_tables", lambda connection: (head, line))
    monkeypatch.setattr(InvoiceService, "_engine", lambda self: engine)
    yield InvoiceService(engine), owner, engine
    engine.dispose()


def test_query_scope_pagination_and_currency_totals(query_service):
    service, owner, _ = query_service
    data = service.list_invoices(InvoiceQuery(page_size=1), owner)
    assert data["total"] == 2 and len(data["rows"]) == 1 and data["hasNext"]
    assert data["rows"][0]["id"] == "2"
    assert {a["currency"]: a["gross"] for a in data["amounts"]} == {None: "100.123456", "USD": "-10.120000"}
    page = service.list_invoices(InvoiceQuery(page_size=1, page=2), owner)
    assert page["rows"][0]["id"] == "1" and page["rows"][0]["lineCount"] == 1
    assert not page["hasNext"] and page["hasPrevious"]
    assert service.list_invoices(InvoiceQuery(), "other")["total"] == 0


def test_search_dates_status_and_literal_wildcards(query_service):
    service, owner, _ = query_service
    assert service.list_invoices(InvoiceQuery(q="100%"), owner)["total"] == 2
    assert service.list_invoices(InvoiceQuery(q="_"), owner)["total"] == 0
    assert service.list_invoices(InvoiceQuery(status="red_offset"), owner)["total"] == 1
    assert service.list_invoices(InvoiceQuery(date_from=date(2026, 9, 1)), owner)["total"] == 0


def test_detail_does_not_leak_other_identity_or_inactive_records(query_service):
    service, owner, _ = query_service
    detail = service.invoice_detail(1, owner)
    assert detail["lineCount"] == 1 and detail["lines"][0]["quantity"] == "29.24937028"
    assert "tenant_id" not in detail and "source_data" not in detail
    for invoice_id in (3, 4, 5, 999):
        with pytest.raises(ApiError) as error:
            service.invoice_detail(invoice_id, owner)
        assert error.value.status == 404
    with pytest.raises(ApiError):
        service.invoice_detail(1, "other")


def test_query_http_auth_and_invalid_filters(context, query_service):
    _, _, engine = query_service
    with TestClient(
        create_app(context.settings, context.ns, context.engine, business_engine=engine)
    ) as client:
        assert client.get("/api/invoices").status_code == 401
        assert client.get("/api/invoices/1").status_code == 401
        headers = {"Authorization": f"Bearer {context.settings.service_key}"}
        response = client.get("/api/invoices", headers=headers)
        assert response.status_code == 200 and response.json()["total"] == 2
        assert client.get("/api/invoices/1", headers=headers).status_code == 200
        assert client.get("/api/invoices/3", headers=headers).status_code == 404
        for query in (
            "page=0",
            "page_size=101",
            "status=matched",
            "date_from=invalid",
            "date_from=2026-09-01&date_to=2026-08-01",
        ):
            assert client.get(f"/api/invoices?{query}", headers=headers).status_code == 400


def test_batch_details_preserve_visibility_and_lines(query_service):
    service, owner, _engine = query_service
    rows = service.invoice_details([1, 2], owner)
    assert {row["id"] for row in rows} == {"1", "2"}
    assert next(row for row in rows if row["id"] == "1")["lines"] == service.invoice_detail(1, owner)["lines"]
    for ids in ([1, 3], [4], [5], [999]):
        with pytest.raises(ApiError) as error:
            service.invoice_details(ids, owner)
        assert error.value.status == 404
    with pytest.raises(ApiError):
        service.invoice_details([1], "other")
