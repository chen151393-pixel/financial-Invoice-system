"""发票文件批量上传：按发票号码找到比对通过的子采购单，归档到报关单文件夹，不猜测、不覆盖。"""

import base64
from pathlib import Path

import pytest
from backend.core.errors import ApiError
from backend.modules.matching.dto.invoice_file_dto import InvoiceFileUpload
from backend.modules.matching.dto.matching_dto import ConfirmBody
from backend.modules.matching.service.invoice_file_service import InvoiceFileService, _numbers
from backend.modules.source.public import SourceDirectory
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id, proposals
from backend.tests.test_matching import world as world  # 共用夹具
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具
from backend.tests.test_task import USER, approve, task_rows
from backend.tests.test_task import app_services as app_services  # 共用夹具

PDF = b"%PDF-1.4\ninvoice\n%%EOF"
NUMBER = "26000000000000006601"


@pytest.fixture
def files(engine, app_services):
    return InvoiceFileService(engine, SourceDirectory(engine), app_services["tasks"].archive)


@pytest.fixture
def imported(ns, engine, app_services, world):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(app_services, "CD870")
    import_invoices(world, [invoice(NUMBER, [INK, FLUID], remark="SUB-200")])
    return invoice_id(engine, NUMBER)


def confirm_all(world, number_id):
    for proposal in proposals(world, number_id):
        world["allocations"].confirm(int(proposal.id), ConfirmBody(), USER)


def upload(files, items, actor=USER):
    body = InvoiceFileUpload(
        files=[
            {"filename": name, "content": base64.b64encode(content).decode(), "invoiceNo": number}
            for name, content, number in items
        ]
    )
    return files.upload(body, actor).items


def test_filename_numbers_ignore_digits_inside_longer_runs():
    assert _numbers(f"dzfp_{NUMBER}_上海供应商_20260729103015") == [NUMBER, "20260729103015"]
    assert _numbers("123456789012345678901234") == []
    assert _numbers("扫描件1234567") == []


def test_unconfirmed_invoice_is_not_archived(engine, files, imported):
    items = upload(files, [(f"dzfp_{NUMBER}.pdf", PDF, "")])
    assert items[0].status == "not_ready" and items[0].invoiceNumber == NUMBER
    assert "尚未比对通过" in items[0].reason
    assert rows(engine, "SELECT id FROM matching_invoice_files") == []


def test_confirmed_invoice_is_saved_to_declaration_folder_without_overwrite(engine, files, world, imported):
    confirm_all(world, imported)
    statuses = [row["status"] for row in task_rows(engine)]
    items = upload(
        files,
        [
            (f"dzfp_{NUMBER}_上海供应商_20260729103015.pdf", PDF, ""),
            ("扫描件.pdf", PDF, ""),
            ("手工指定.pdf", PDF, "99999999999999999999"),
            (f"{NUMBER}.txt", b"plain text", ""),
        ],
    )
    assert [(item.status, item.invoiceNumber) for item in items] == [
        ("saved", NUMBER),
        ("unmatched", ""),
        ("unmatched", "99999999999999999999"),
        ("failed", ""),
    ]
    path = Path(items[0].archivePaths[0])
    assert path.name == f"发票_{NUMBER}.pdf" and path.parent.name == "CD870_REAL870"
    assert path.read_bytes() == PDF
    assert "未能从文件名识别" in items[1].reason and "仅支持" in items[3].reason
    record = rows(engine, "SELECT * FROM matching_invoice_files")
    assert len(record) == 1 and record[0]["invoice_id"] == imported and record[0]["uploaded_by"] == USER
    again = upload(files, [("任意名称.pdf", PDF, NUMBER), (f"{NUMBER}-新版.pdf", PDF + b" ", "")])
    assert again[0].status == "saved" and "相同文件" in again[0].reason
    assert again[1].status == "conflict" and "CD870" in again[1].reason and path.read_bytes() == PDF
    # 只归档文件，不改变任务状态
    assert [row["status"] for row in task_rows(engine)] == statuses


def test_ambiguous_numbers_and_read_only_identity(files, world, imported):
    confirm_all(world, imported)
    import_invoices(world, [invoice("26000000000000006602", [INK], remark="SUB-200")], name="b.xlsx")
    items = upload(files, [(f"{NUMBER}与26000000000000006602.pdf", PDF, "")])
    assert items[0].status == "ambiguous" and NUMBER in items[0].reason
    with pytest.raises(ApiError) as error:
        upload(files, [(f"{NUMBER}.pdf", PDF, "")], actor="service:feishu")
    assert error.value.status == 403


def test_http_route_requires_login_and_files(context, engine, tmp_path):
    from dataclasses import replace

    from backend.app import create_app
    from fastapi.testclient import TestClient

    settings = replace(context.settings, subpo_archive_root=tmp_path)
    with TestClient(create_app(settings, context.ns, engine)) as client:
        path = "/api/matching/invoice-files/upload"
        assert client.post(path, json={"files": []}).status_code == 401
        headers = {"Origin": settings.origin}
        login = client.post(
            "/api/session", headers=headers, json={"username": "admin", "password": settings.admin_password}
        )
        assert login.status_code == 200
        assert client.post(path, json={"files": []}, headers=headers).status_code == 400
        body = {"files": [{"filename": f"{NUMBER}.pdf", "content": base64.b64encode(PDF).decode()}]}
        result = client.post(path, json=body, headers=headers)
        assert result.status_code == 200 and result.json()["items"][0]["status"] == "unmatched"
