"""invoice 模块：Excel 预览与确认、去重与冲突、业务类型筛选、事件、列表与详情、HTTP。

使用仓库虚构的 lemon-invoices.xls（3 票 4 行）与内存生成的 XLSX；SQLite 隔离库，不连接柠檬云。
"""

import base64
from pathlib import Path

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.core.events import EventBus
from backend.modules.invoice.dto.import_dto import ImportBody
from backend.modules.invoice.dto.invoice_dto import InvoiceQuery
from backend.modules.invoice.public import InvoicesImported
from backend.modules.invoice.service.import_service import ImportService
from backend.modules.invoice.service.invoice_service import InvoiceService
from backend.tests.invoice_files import invoice, workbook
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import rows
from fastapi.testclient import TestClient

USER = "user:admin"
XLS = base64.b64encode((Path(__file__).parent / "fixtures" / "lemon-invoices.xls").read_bytes()).decode()


@pytest.fixture
def published():
    return []


@pytest.fixture
def imports(engine, published):
    events = EventBus()
    events.subscribe(InvoicesImported, lambda connection, event: published.append(event))
    return ImportService(engine, events)


def run(imports, content=XLS, filename="lemon-invoices.xls", actor=USER):
    preview = imports.process(ImportBody(filename=filename, content=content), actor)
    body = ImportBody(filename=filename, content=content, previewToken=preview.previewToken)
    return preview, imports.process(body, actor, commit=True)


def test_preview_then_confirm_saves_headers_items_and_raw(engine, imports, published):
    preview, saved = run(imports)
    assert (preview.invoiceCount, preview.created, preview.saved, saved.saved) == (3, 3, False, True)
    assert saved.created == 3
    headers = rows(engine, "SELECT * FROM invoice_headers ORDER BY invoice_no")
    assert [h["status"] for h in headers] == ["normal", "red_offset", "normal"]
    assert headers[0]["invoice_key"] == ":26000000000000000001" and headers[0]["currency"] == "CNY"
    assert headers[0]["seller_name_normalized"] == "隔离测试供应商" and headers[0]["source"] == "lemon_excel"
    assert len(rows(engine, "SELECT id FROM invoice_items")) == 4
    assert len(rows(engine, "SELECT id FROM invoice_raw_records")) == 3
    assert [sorted(event.invoice_ids) for event in published] == [sorted(h["id"] for h in headers)]


def test_reimport_same_content_is_unchanged(engine, imports, published):
    run(imports)
    preview, saved = run(imports)
    assert (preview.unchanged, preview.created, saved.created) == (3, 0, 0)
    assert len(rows(engine, "SELECT id FROM invoice_headers")) == 3 and len(published) == 1


def test_changed_content_creates_immutable_version(engine, imports):
    first = workbook([invoice("26000000000000009001", [("墨水", "个", "10", "100.00", "13.00")])])
    run(imports, first, "a.xlsx")
    changed = workbook(
        [
            invoice("26000000000000009001", [("墨水", "个", "10", "90.00", "11.70")]),
            invoice("26000000000000009002", [("清洗液", "个", "1", "10.00", "1.30")]),
        ]
    )
    preview = imports.process(ImportBody(filename="b.xlsx", content=changed), USER)
    assert preview.updated == 1 and preview.allowed
    saved = imports.process(
        ImportBody(filename="b.xlsx", content=changed, previewToken=preview.previewToken), USER, commit=True
    )
    assert saved.updated == 1 and saved.created == 1
    assert len(rows(engine, "SELECT id FROM invoice_headers")) == 2
    assert len(rows(engine, "SELECT id FROM invoice_versions")) == 3


def test_only_fixed_asset_purchases_are_imported(engine, imports):
    content = workbook(
        [
            invoice("26000000000000009011", [("墨水", "个", "1", "1.00", "0.13")]),
            invoice(
                "26000000000000009012", [("办公用品", "个", "1", "1.00", "0.13")], business="采购办公用品"
            ),
        ]
    )
    preview, saved = run(imports, content, "c.xlsx")
    assert (preview.sourceInvoiceCount, preview.invoiceCount, preview.excludedCount) == (2, 1, 1)
    assert [h["invoice_no"] for h in rows(engine, "SELECT invoice_no FROM invoice_headers")] == [
        "26000000000000009011"
    ]


def test_token_and_identity_checks(imports):
    with pytest.raises(ApiError) as error:
        imports.process(
            ImportBody(filename="lemon-invoices.xls", content=XLS, previewToken="1.x"), USER, commit=True
        )
    assert error.value.status == 409
    preview = imports.process(ImportBody(filename="lemon-invoices.xls", content=XLS), USER)
    with pytest.raises(ApiError) as error:
        imports.process(
            ImportBody(filename="lemon-invoices.xls", content=XLS, previewToken=preview.previewToken),
            "service:bot",
            commit=True,
        )
    assert error.value.status == 403


def test_list_filters_amounts_and_detail(engine, imports):
    run(imports)
    service = InvoiceService(engine)
    listed = service.browse(InvoiceQuery())
    assert listed.total == 3 and listed.amounts[0].currency == "CNY"
    assert listed.amounts[0].gross == "120.40"
    assert service.browse(InvoiceQuery(status="red_offset")).total == 1
    assert service.browse(InvoiceQuery(q="0000000003")).total == 1
    assert service.browse(InvoiceQuery(page_size=2, page=2)).rows[0].number == "26000000000000000001"
    first = next(row for row in listed.rows if row.number.endswith("0001"))
    detail = service.detail(int(first.id))
    assert detail.lines[0].taxRate == "13%" and detail.lines[0].gross == "113.00"
    assert detail.source == "Excel导入" and detail.buyer is None
    with pytest.raises(ApiError) as error:
        service.detail(999999)
    assert error.value.status == 404


def test_http_import_and_list(context, engine):
    app = create_app(context.settings, context.ns, engine)
    with TestClient(app) as client:
        assert client.get("/api/invoices").status_code == 401
        headers = {"Origin": context.settings.origin}
        login = client.post(
            "/api/session",
            headers=headers,
            json={"username": "admin", "password": context.settings.admin_password},
        )
        assert login.status_code == 200
        assert client.get("/api/invoices/import/configuration", headers=headers).json()["allowed"]
        body = {"filename": "lemon-invoices.xls", "content": XLS}
        preview = client.post("/api/invoices/import/preview", json=body, headers=headers)
        assert preview.status_code == 200
        token = preview.json()["previewToken"]
        saved = client.post(
            "/api/invoices/import/confirm", json={**body, "previewToken": token}, headers=headers
        )
        assert saved.status_code == 200 and saved.json()["created"] == 3
        listed = client.get("/api/invoices?page_size=2", headers=headers).json()
        assert listed["total"] == 3 and len(listed["rows"]) == 2
        assert client.get("/api/invoices/0", headers=headers).status_code == 400


def test_stale_preview_cannot_overwrite_a_newer_version(imports, engine):
    first = workbook([invoice("26000000000000009991", [("墨水", "个", "1", "10.00", "1.30")])])
    run(imports, first, "a.xlsx")
    stale = workbook([invoice("26000000000000009991", [("墨水", "个", "1", "20.00", "2.60")])])
    preview = imports.process(ImportBody(filename="b.xlsx", content=stale), USER)
    latest = workbook([invoice("26000000000000009991", [("墨水", "个", "1", "30.00", "3.90")])])
    run(imports, latest, "c.xlsx")
    with pytest.raises(ApiError, match="版本已变化"):
        imports.process(
            ImportBody(filename="b.xlsx", content=stale, previewToken=preview.previewToken), USER, commit=True
        )
    assert len(rows(engine, "SELECT id FROM invoice_versions")) == 2
