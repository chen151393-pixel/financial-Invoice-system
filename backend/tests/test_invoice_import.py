"""使用虚构XLS和隔离MySQL验证导入，不写真实业务库。"""

import base64
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
import xlrd
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.invoice import dao
from backend.modules.invoice import service as invoice_service
from backend.modules.invoice.dto import ImportBody
from backend.modules.invoice.entity import load_tables
from backend.modules.invoice.parser import HEADERS, LINE_HEADERS, build_documents, parse_file, rows
from backend.modules.invoice.service import InvoiceService
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, func, select

FIXTURE = Path(__file__).parent / "fixtures" / "lemon-invoices.xls"


def body():
    return ImportBody(filename=FIXTURE.name, content=base64.b64encode(FIXTURE.read_bytes()).decode())


def source_rows():
    book = xlrd.open_workbook(FIXTURE)
    return rows(book.sheet_by_name("发票信息"), HEADERS, book.datemode), rows(
        book.sheet_by_name("货物信息"), LINE_HEADERS, book.datemode
    )


def test_xls_precision_sign_and_tax_treatments():
    docs, _ = parse_file(body().filename, body().content)
    assert len(docs) == 3
    assert sum(len(doc["lines"]) for doc in docs) == 4
    assert docs[0]["lines"][0]["quantity"] == Decimal("29.24937028")
    assert docs[1]["head"]["invoice_status"] == "red_offset"
    assert docs[1]["head"]["amount_including_tax"] == Decimal("-22.6")
    assert [line["tax_treatment"] for line in docs[2]["lines"]] == ["exempt", "non_taxable"]
    assert all(line["tax_rate"] is None and line["quantity"] is None for line in docs[2]["lines"])


def xlsx_body(change=None):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, headers, data in zip(
        ("发票信息", "货物信息"), (HEADERS, LINE_HEADERS), source_rows(), strict=True
    ):
        sheet = workbook.create_sheet(name)
        sheet.append(headers)
        for _, values in data:
            sheet.append([values[header] for header in headers])
    if change:
        change(workbook)
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return ImportBody(filename="发票测试.xlsx", content=base64.b64encode(stream.getvalue()).decode())


def test_xlsx_matches_xls_content_and_import_identity():
    request = xlsx_body()
    actual, _ = parse_file(request.filename, request.content)
    expected, _ = parse_file(body().filename, body().content)
    assert actual == expected


def combined_body(change=None):
    heads, lines = source_rows()
    book = Workbook()
    sheet = book.active
    sheet.title = "任意表名"
    sheet.append(HEADERS + LINE_HEADERS[4:])
    for _, head in heads:
        details = [line for _, line in lines if line["发票号码"] == head["发票号码"]]
        for line in details:
            sheet.append([head[name] for name in HEADERS] + [line[name] for name in LINE_HEADERS[4:]])
        subtotal = {name: None for name in LINE_HEADERS[4:]}
        subtotal.update(商品名称="合计", 金额=head["合计金额"], 税额=head["合计税额"])
        sheet.append([head[name] for name in HEADERS] + [subtotal[name] for name in LINE_HEADERS[4:]])
    if change:
        change(sheet)
    stream = BytesIO()
    book.save(stream)
    book.close()
    return ImportBody(filename="合并.xlsx", content=base64.b64encode(stream.getvalue()).decode())


def test_combined_sheet_groups_headers_omits_totals_and_preserves_identity():
    request = combined_body()
    actual, _ = parse_file(request.filename, request.content)
    expected, _ = parse_file(body().filename, body().content)
    assert [(d["head"], d["lines"]) for d in actual] == [(d["head"], d["lines"]) for d in expected]
    assert len(actual) == 3 and sum(len(d["lines"]) for d in actual) == 4
    assert all(d["rawHead"]["sheet"] == "任意表名" for d in actual)
    assert all(d["rawHead"]["subtotal"]["values"]["商品名称"] == "合计" for d in actual)
    assert all(r["sheet"] == "任意表名" for d in actual for r in d["rawLines"])


@pytest.mark.parametrize(
    "kind,message", [("head", "票头字段不一致"), ("subtotal", "金额不一致"), ("quantity", "数量")]
)
def test_combined_sheet_rejects_inconsistent_repeated_heads_or_totals(kind, message):
    def change(sheet):
        if kind == "head":
            sheet.cell(3, HEADERS.index("供应商名称") + 1).value = "不同供应商"
        else:
            field = "金额" if kind == "subtotal" else "数量"
            sheet.cell(3, len(HEADERS) + LINE_HEADERS[4:].index(field) + 1).value = 999

    request = combined_body(change)
    with pytest.raises(ApiError, match=message):
        parse_file(request.filename, request.content)


def test_xlsx_native_dates_numbers_and_percent():
    def change(book):
        for name, headers in [("发票信息", HEADERS), ("货物信息", LINE_HEADERS)]:
            sheet = book[name]
            cell = sheet.cell(2, headers.index("开票日期") + 1)
            cell.value = datetime.fromisoformat(cell.value)
            if name == "货物信息":
                rate = sheet.cell(2, headers.index("税率") + 1)
                rate.value, rate.number_format = 0.13, "0%"
        book["货物信息"].cell(2, LINE_HEADERS.index("数量") + 1).value = 29.24937028

    request = xlsx_body(change)
    actual, _ = parse_file(request.filename, request.content)
    expected, _ = parse_file(body().filename, body().content)
    assert actual == expected


@pytest.mark.parametrize(
    "mutation,message",
    [
        ("formula", "公式"),
        ("number", "须为文本"),
        ("error", "错误值"),
        ("header", "表头"),
        ("sheet", "工作表"),
        ("far_row", "6000行"),
        ("far_column", "列数"),
    ],
)
def test_xlsx_rejects_invalid_workbook(mutation, message):
    def change(book):
        sheet = book["发票信息"]
        if mutation == "formula":
            sheet.cell(2, HEADERS.index("合计金额") + 1).value = "=100"
        elif mutation == "number":
            sheet.cell(2, HEADERS.index("发票号码") + 1).value = 12345678901234567890
        elif mutation == "error":
            sheet.cell(2, HEADERS.index("合计金额") + 1).value = "#DIV/0!"
        elif mutation == "header":
            sheet.cell(1, 1).value = "错误表头"
        elif mutation == "sheet":
            book.remove(book["货物信息"])
        elif mutation == "far_row":
            sheet.cell(6010, 1).value = "不可静默截断"
        else:
            sheet.cell(2, 30).value = "多余列"

    request = xlsx_body(change)
    with pytest.raises(ApiError, match=message):
        parse_file(request.filename, request.content)


def test_xlsx_rejects_renamed_xls_and_zip_expansion():
    from zipfile import ZIP_DEFLATED, ZipFile

    with pytest.raises(ApiError, match="XLSX"):
        parse_file("renamed.xlsx", body().content)
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr("oversized.xml", b"0" * (32 * 1024 * 1024 + 1))
    with pytest.raises(ApiError, match="解压后过大"):
        parse_file("large.xlsx", base64.b64encode(stream.getvalue()).decode())


@pytest.mark.parametrize(
    "mutation,message",
    [
        ("duplicate", "重复"),
        ("orphan", "找不到"),
        ("unbalanced", "汇总"),
        ("long_number", "20位"),
        ("period", "期间"),
        ("precision", "精度"),
        ("line_date", "不一致"),
        ("empty", "1至1000"),
    ],
)
def test_invalid_rows(mutation, message):
    heads, lines = source_rows()
    if mutation == "duplicate":
        heads.append(deepcopy(heads[0]))
    if mutation == "orphan":
        lines[0][1]["发票号码"] = "0" * 20
    if mutation == "unbalanced":
        lines[0][1]["税额"] = "12"
    if mutation == "long_number":
        heads[0][1]["发票号码"] = "123"
    if mutation == "period":
        heads[0][1]["记账期间"] = "2026-13"
    if mutation == "precision":
        lines[0][1]["数量"] = "1.123456789"
    if mutation == "line_date":
        lines[0][1]["开票日期"] = "2026-08-01"
    if mutation == "empty":
        heads = []
    with pytest.raises(ApiError, match=message):
        build_documents(heads, lines)


def test_reorder_and_duplicate_lines_keep_content_identity():
    heads, lines = source_rows()
    original = build_documents(heads, lines)
    assert [d["head"]["content_hash"] for d in original] == [
        d["head"]["content_hash"] for d in build_documents(heads, list(reversed(lines)))
    ]
    heads[0][1].update({"合计金额": "200", "合计税额": "26", "价税合计": "226"})
    lines.append(deepcopy(lines[0]))
    doc = build_documents(heads, lines)[0]
    assert len({line["source_line_key"] for line in doc["lines"]}) == 2


@pytest.mark.parametrize(
    "filename,content",
    [
        ("x.xlsx", "a"),
        ("../x.xls", "a"),
        ("x.xls", "invalid!"),
        ("x.xls", base64.b64encode(b"fake").decode()),
    ],
)
def test_invalid_file(filename, content):
    with pytest.raises(ApiError):
        parse_file(filename, content)


def test_auth_extra_fields_and_upload_boundary(context):
    with TestClient(create_app(context.settings, context.ns, context.engine)) as client:
        path = "/api/invoices/import/preview"
        assert client.post(path, json=body().model_dump()).status_code == 401
        headers = {"Authorization": f"Bearer {context.settings.service_key}"}
        assert (
            client.post(path, headers=headers, json={**body().model_dump(), "tenant_id": "other"}).status_code
            == 400
        )
        assert client.post(path, headers=headers, json=body().model_dump()).status_code == 503
        large = {"content": "a" * (129 * 1024), "filename": "test.xls"}
        assert client.post("/api/ns/connect", headers=headers, json=large).status_code == 413
        assert client.post(path, headers=headers, json=large).status_code == 503
        assert client.post(path, headers=headers, content=b"a" * (6 * 1024 * 1024 + 1)).status_code == 415
        assert (
            client.post(
                path,
                headers={**headers, "Content-Type": "application/json"},
                content=b"a" * (6 * 1024 * 1024 + 1),
            ).status_code
            == 413
        )


@pytest.fixture
def mysql_import():
    url = os.environ.get("INVOICE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("未配置隔离发票MySQL测试库")
    engine = create_engine(url, pool_pre_ping=True)
    assert engine.dialect.name == "mysql" and engine.url.database.endswith("_invoice_test")
    owner = f"invoice-test-{uuid4().hex}"
    service = InvoiceService(engine)
    try:
        yield service, owner
    finally:
        with engine.begin() as connection:
            head, line = load_tables(connection)
            tenants = [hashlib.sha256(value.encode()).hexdigest() for value in (owner, owner + "other")]
            connection.execute(line.delete().where(line.c.tenant_id.in_(tenants)))
            connection.execute(head.delete().where(head.c.tenant_id.in_(tenants)))
        engine.dispose()


def preview_and_confirm(service, owner):
    request = body()
    preview = service.process(request, owner)
    request.previewToken = preview["previewToken"]
    return service.process(request, owner, commit=True)


def test_mysql_repeat_isolation_and_precise_storage(mysql_import):
    service, owner = mysql_import
    assert service.configuration()["allowed"]
    result = preview_and_confirm(service, owner)
    assert result["created"] == 3 and result["saved"]
    assert preview_and_confirm(service, owner)["unchanged"] == 3
    assert preview_and_confirm(service, owner + "other")["created"] == 3
    with service.engine.connect() as connection:
        head, line = load_tables(connection)
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        assert (
            connection.scalar(select(func.count()).select_from(line).where(line.c.tenant_id == tenant)) == 4
        )
        assert connection.scalar(
            select(line.c.quantity).where(line.c.tenant_id == tenant, line.c.item_name == "商品甲")
        ) == Decimal("29.24937028")
        stored = connection.execute(select(head).where(head.c.tenant_id == tenant)).mappings().first()
        assert stored["validation_status"] == "review"
        assert stored["source_data"]["file_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()


def test_mysql_preview_token_and_conflict(mysql_import):
    service, owner = mysql_import
    request = body()
    request.previewToken = service.process(request, owner)["previewToken"]
    with pytest.raises(ApiError, match="预览"):
        service.process(request, owner + "other", commit=True)
    changed = request.model_copy(update={"filename": "different.xls"})
    with pytest.raises(ApiError, match="预览"):
        service.process(changed, owner, commit=True)
    service.process(request, owner, commit=True)
    with service.engine.begin() as connection:
        head, _ = load_tables(connection)
        connection.execute(
            head.update()
            .where(head.c.tenant_id == hashlib.sha256(owner.encode()).hexdigest())
            .values(content_hash="changed")
        )
    assert service.process(body(), owner)["conflicts"] == 3
    with pytest.raises(ApiError, match="冲突"):
        service.process(request, owner, commit=True)


def test_mysql_atomic_rollback(mysql_import, monkeypatch):
    service, owner = mysql_import
    original = dao.insert
    calls = 0

    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ApiError(422, "故障注入")
        return original(*args)

    monkeypatch.setattr(dao, "insert", fail_second)
    with pytest.raises(ApiError, match="故障注入"):
        preview_and_confirm(service, owner)
    assert service.process(body(), owner)["created"] == 3


def test_mysql_concurrent_same_file(mysql_import):
    service, owner = mysql_import
    request = body()
    request.previewToken = service.process(request, owner)["previewToken"]

    def save():
        try:
            return service.process(request, owner, commit=True)
        except ApiError as error:
            assert error.status == 409
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: save(), range(2)))
    assert sum(result["created"] for result in results if result) == 3
    assert service.process(body(), owner)["unchanged"] == 3


def test_mysql_http_confirmation(context, mysql_import):
    service, _ = mysql_import
    # 使用独立测试身份；测试结束前清理本测试创建的租户记录。
    owner = "service:feishu"
    with TestClient(create_app(context.settings, context.ns, context.engine, service.engine)) as client:
        headers = {"Authorization": f"Bearer {context.settings.service_key}"}
        request = body().model_dump()
        preview = client.post("/api/invoices/import/preview", headers=headers, json=request)
        assert preview.status_code == 200
        request["previewToken"] = preview.json()["previewToken"]
        saved = client.post("/api/invoices/import/confirm", headers=headers, json=request)
        assert saved.status_code == 200 and saved.json()["saved"]
    # 精确定位原始审计操作者，而非对测试库执行全表清空。
    with service.engine.begin() as connection:
        head, line = load_tables(connection)
        records = connection.execute(select(head.c.id, head.c.tenant_id, head.c.source_data)).mappings().all()
        for record in records:
            if record["source_data"]["imported_by"] == owner:
                connection.execute(
                    line.delete().where(
                        line.c.invoice_id == record["id"], line.c.tenant_id == record["tenant_id"]
                    )
                )
                connection.execute(head.delete().where(head.c.id == record["id"]))


def test_mysql_business_type_filter_and_empty(mysql_import, monkeypatch):
    service, owner = mysql_import
    parsed, file_hash = parse_file(body().filename, body().content)
    parsed[1]["head"]["business_type_name"] = "办公费"
    monkeypatch.setattr(invoice_service, "parse_file", lambda *_: (deepcopy(parsed), file_hash))
    preview = service.process(body(), owner)
    assert (preview["sourceInvoiceCount"], preview["invoiceCount"], preview["excludedCount"]) == (3, 2, 1)
    assert Decimal(preview["amount"]) == Decimal("143")
    assert all(row["businessType"] == "采购固定资产" for row in preview["rows"])
    request = body().model_copy(update={"previewToken": preview["previewToken"]})
    saved = service.process(request, owner, commit=True)
    assert saved["created"] == 2
    with service.engine.connect() as connection:
        head, line = load_tables(connection)
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        assert (
            connection.scalar(select(func.count()).select_from(head).where(head.c.tenant_id == tenant)) == 2
        )
        assert (
            connection.scalar(select(func.count()).select_from(line).where(line.c.tenant_id == tenant)) == 3
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(head)
                .where(head.c.tenant_id == tenant, head.c.business_type_name != "采购固定资产")
            )
            == 0
        )
    for doc in parsed:
        doc["head"]["business_type_name"] = "办公费"
    empty = service.process(body(), owner)
    assert not empty["allowed"] and empty["invoiceCount"] == 0 and empty["excludedCount"] == 3
    request.previewToken = empty["previewToken"]
    with pytest.raises(ApiError, match="没有业务类型"):
        service.process(request, owner, commit=True)
