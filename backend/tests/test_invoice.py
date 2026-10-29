"""invoice 模块：Excel 预览与确认、去重与冲突、业务类型筛选、事件、列表与详情、HTTP。

使用仓库虚构的 lemon-invoices.xls（3 票 4 行）与内存生成的 XLSX；SQLite 隔离库，不连接柠檬云。
"""

import base64
from decimal import Decimal
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
from backend.modules.invoice.service.invoice_stats_service import InvoiceStatsService
from backend.tests.invoice_files import invoice, workbook
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import rows
from fastapi.testclient import TestClient
from sqlalchemy import text

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


def test_default_purchase_types_are_imported_and_other_types_excluded(engine, imports):
    content = workbook(
        [
            invoice("26000000000000009011", [("墨水", "个", "1", "1.00", "0.13")]),
            invoice(
                "26000000000000009012", [("办公用品", "个", "1", "1.00", "0.13")], business="采购办公用品"
            ),
            invoice("26000000000000009013", [("刻字贴", "卷", "2", "10.00", "1.30")], business="采购支出"),
        ]
    )
    preview, saved = run(imports, content, "c.xlsx")
    assert (preview.sourceInvoiceCount, preview.invoiceCount, preview.excludedCount) == (3, 2, 1)
    assert saved.created == 2 and saved.amount == "12.43"
    assert preview.rows[1].businessType == "采购支出"
    assert [
        h["invoice_no"] for h in rows(engine, "SELECT invoice_no FROM invoice_headers ORDER BY invoice_no")
    ] == ["26000000000000009011", "26000000000000009013"]
    assert (
        rows(engine, "SELECT business_type FROM invoice_headers WHERE invoice_no='26000000000000009013'")[0][
            "business_type"
        ]
        == "采购支出"
    )
    duplicate, _ = run(imports, content, "c.xlsx")
    assert duplicate.unchanged == 2 and duplicate.excludedCount == 1


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
    assert service.browse(InvoiceQuery(status="red_letter")).total == 1
    assert service.browse(InvoiceQuery(q="0000000003")).total == 1
    assert service.browse(InvoiceQuery(page_size=2, page=2)).rows[0].number == "26000000000000000001"
    first = next(row for row in listed.rows if row.number.endswith("0001"))
    detail = service.detail(int(first.id))
    assert detail.lines[0].taxRate == "13%" and detail.lines[0].gross == "113.00"
    assert detail.source == "Excel导入" and detail.buyer is None
    with pytest.raises(ApiError) as error:
        service.detail(999999)
    assert error.value.status == 404


def test_stats_follow_list_filters(engine, imports):
    run(imports)
    stats = InvoiceStatsService(engine).stats(InvoiceQuery())
    counts = {item.key: item.count for item in stats.statuses}
    assert list(counts) == ["normal", "red_letter", "red_offset", "void", "unknown"]
    assert counts["red_letter"] == 1 and sum(counts.values()) == stats.total == 3  # 与列表的展示状态一致
    assert len(stats.months) == 6 and sum(item.count for item in stats.months) == 3
    assert stats.months == sorted(stats.months, key=lambda item: item.month)
    assert [(item.count) for item in stats.accounts] == [3]
    # 人民币金额：按月与按账套合计一致，等于列表的人民币价税合计
    listed = InvoiceService(engine).browse(InvoiceQuery())
    cny = next(item.gross for item in listed.amounts if item.currency == "CNY")
    assert stats.accounts[0].gross == cny == f"{sum(Decimal(m.gross) for m in stats.months):.2f}"
    assert stats.otherCurrencyCount == 0
    red = InvoiceStatsService(engine).stats(InvoiceQuery(status="red_letter"))
    assert sum(item.count for item in red.statuses) == 1 and red.accounts[0].count == 1
    empty = InvoiceStatsService(engine).stats(InvoiceQuery(q="不存在"))
    assert empty.accounts == [] and sum(item.count for item in empty.months) == 0


@pytest.mark.parametrize(
    ("source_status", "query_status", "label"),
    [("已红冲", "red_offset", "已被红冲"), ("已被红冲", "red_offset", "已被红冲"), ("作废", "void", "作废")],
)
def test_status_filter_keeps_pagination_totals_and_detail_consistent(
    engine, imports, source_status, query_status, label
):
    content = workbook(
        [
            invoice("26000000000000009101", [("普通商品", "个", "1", "10.00", "1.30")]),
            invoice("26000000000000009102", [("异常商品", "个", "1", "20.00", "2.60")], status=source_status),
            invoice("26000000000000009103", [("异常商品", "个", "1", "30.00", "3.90")], status=source_status),
        ]
    )
    run(imports, content, "status.xlsx")
    service = InvoiceService(engine)
    result = service.browse(InvoiceQuery(status=query_status, page_size=1, page=2))
    assert result.total == 2 and len(result.rows) == 1
    assert result.amounts[0].gross == "56.50"
    row = result.rows[0]
    assert row.sourceStatus == query_status and row.status == label and row.statusNotice
    assert service.detail(int(row.id)).statusNotice == row.statusNotice
    normal = service.browse(InvoiceQuery(status="normal")).rows[0]
    assert normal.status == "正常" and normal.statusNotice is None
    assert service.browse(InvoiceQuery(status=query_status, q="不存在")).total == 0


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
        red = client.get("/api/invoices?status=red_letter", headers=headers).json()
        assert red["total"] == 1 and red["rows"][0]["displayStatus"] == "red_letter"
        totals = client.get("/api/matching/invoice-totals?status=red_letter", headers=headers).json()
        assert totals["amounts"][0]["count"] == 1
        stats = client.get("/api/invoices/stats?status=red_letter", headers=headers).json()
        assert sum(item["count"] for item in stats["statuses"]) == 1
        assert client.get("/api/invoices/0", headers=headers).status_code == 400


def test_independent_search_fields_share_list_stats_and_matching_scope(context, engine, imports):
    run(
        imports,
        workbook(
            [
                invoice("26000000000000000111", [("商品", "个", "1", "10.00", "1.30")], seller="甲供应商"),
                invoice("26000000000000000222", [("商品", "个", "1", "20.00", "2.60")], seller="乙供应商111"),
            ]
        ),
        "fields.xlsx",
    )
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE invoice_headers SET seller_tax_no = 'TAX111' WHERE seller_name = '甲供应商'")
        )
        connection.execute(
            text("UPDATE invoice_headers SET seller_tax_no = 'TAX222' WHERE seller_name = '乙供应商111'")
        )
    app = create_app(context.settings, context.ns, engine)
    with TestClient(app) as client:
        origin = {"Origin": context.settings.origin}
        assert (
            client.post(
                "/api/session",
                headers=origin,
                json={
                    "username": "admin",
                    "password": context.settings.admin_password,
                },
            ).status_code
            == 200
        )
        for filters, count, number in [
            ({"invoice_no": " 111 "}, 1, "26000000000000000111"),
            ({"seller_name": "111"}, 1, "26000000000000000222"),
            ({"seller_tax_no": "222"}, 1, "26000000000000000222"),
            ({"invoice_no": "111", "seller_name": "甲", "seller_tax_no": "111"}, 1, "26000000000000000111"),
            ({"invoice_no": "111", "seller_name": "乙"}, 0, None),
            ({"seller_name": "%"}, 0, None),
            ({"seller_tax_no": "_"}, 0, None),
            ({"invoice_no": " "}, 2, None),
        ]:
            listed = client.get("/api/invoices", params=filters)
            assert listed.status_code == 200 and listed.json()["total"] == count
            if number:
                assert listed.json()["rows"][0]["number"] == number
            stats = client.get("/api/invoices/stats", params=filters)
            assert stats.status_code == 200 and stats.json()["total"] == count
            totals = client.get("/api/matching/invoice-totals", params=filters)
            assert totals.status_code == 200
            assert sum(row["count"] for row in totals.json()["amounts"]) == count
            matched = client.post("/api/matching/invoices/query", json=filters, headers=origin)
            assert matched.status_code == 200 and matched.json()["list"]["total"] == count
        for field in ("invoice_no", "seller_name", "seller_tax_no"):
            invalid = {field: "x" * 101}
            assert client.get("/api/invoices", params=invalid).status_code == 400
            assert client.get("/api/matching/invoice-totals", params=invalid).status_code == 400


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
