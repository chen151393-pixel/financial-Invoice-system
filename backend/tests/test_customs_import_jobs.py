"""海关异步导入：真实请求入口、持久队列、失败原子性与格式尾行回归。"""

import base64
import io
from zipfile import ZipFile

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.review.dao import customs_import_job_dao as job_dao
from backend.modules.review.dto.customs_receipt_dto import CustomsImportRequest, CustomsReceiptQuery
from backend.modules.review.service.customs_import_service import CustomsImportService
from backend.modules.review.service.customs_import_worker import CustomsImportWorker
from backend.modules.review.service.customs_receipt_parser import parse
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.tests.test_customs_receipts import HEADERS, row, xlsx
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from fastapi.testclient import TestClient
from openpyxl import Workbook
from openpyxl.styles import PatternFill
from sqlalchemy.exc import OperationalError


@pytest.fixture
def imports(schema_engine, tmp_path):
    return CustomsImportService(schema_engine, CustomsReceiptService(schema_engine), tmp_path / "uploads")


def submit(imports, rows=None, owner="admin"):
    return imports.enqueue(
        CustomsImportRequest(
            filename="回执.xlsx",
            content=xlsx(rows or [row("REAL001", "01", "相纸", "张", 10)]),
        ),
        owner,
    )


def test_queue_does_not_parse_or_write_receipts_before_worker(imports, monkeypatch):
    def cannot_parse(*args):
        raise AssertionError("请求线程不应解析工作簿")

    monkeypatch.setattr("backend.modules.review.service.customs_import_service.parse_bytes", cannot_parse)
    job = submit(imports)
    assert job.status == "pending" and job.result is None
    assert imports.receipts.browse(CustomsReceiptQuery()).total == 0
    assert len(list(imports.upload_root.iterdir())) == 1
    assert imports.browse("other-user").items == []


def test_worker_saves_receipts_and_result_then_removes_staging(imports):
    job = submit(imports)
    CustomsImportWorker(imports).run_once()
    saved = imports.browse("admin").items[0]
    assert saved.id == job.id and saved.status == "completed"
    assert (saved.result.rows, saved.result.created) == (1, 1)
    assert imports.receipts.browse(CustomsReceiptQuery()).counts.receipts == 1
    assert not list(imports.upload_root.iterdir())
    # 再次消费不会重复导入；刷新页面仍能读取成功记录。
    CustomsImportWorker(imports).run_once()
    assert imports.browse("admin").items[0] == saved


def test_invalid_file_is_visible_failure_and_does_not_replace_old_data(imports):
    original = [row("REAL001", "01", "相纸", "张", 10)]
    submit(imports, original)
    CustomsImportWorker(imports).run_once()
    submit(imports, [row("REAL001", "01", "相纸", "张", 99), row("REAL002", "01", "相纸", "张", "bad")])
    CustomsImportWorker(imports).run_once()
    failed = imports.browse("admin").items[0]
    assert failed.status == "failed" and "成交数量不是有效数值" in failed.error
    assert failed.result is None
    page = imports.receipts.browse(CustomsReceiptQuery())
    assert page.counts.receipts == 1 and page.items[0].revision == 1
    assert page.items[0].groups[0].items[0].quantity == "10"


def test_result_and_receipts_roll_back_together_and_restart_recovers(imports, monkeypatch):
    submit(imports)
    original_finish = job_dao.finish

    def fail_commit(*args, **kwargs):
        raise OperationalError("test", {}, RuntimeError("test database outage"))

    monkeypatch.setattr(job_dao, "finish", fail_commit)
    with pytest.raises(OperationalError):
        CustomsImportWorker(imports).run_once()
    assert imports.browse("admin").items[0].status == "running"
    assert imports.receipts.browse(CustomsReceiptQuery()).total == 0
    assert list(imports.upload_root.iterdir())
    monkeypatch.setattr(job_dao, "finish", original_finish)
    recovered = CustomsImportService(imports.engine, imports.receipts, imports.upload_root)
    CustomsImportWorker(recovered).run_once()
    assert recovered.browse("admin").items[0].status == "completed"


def test_whole_save_rolls_back_on_unexpected_failure(imports, monkeypatch):
    submit(imports)
    save = imports.receipts.save_parsed

    def fail_after_save(*args):
        save(*args)
        raise ValueError("private-data-not-for-browser")

    monkeypatch.setattr(imports.receipts, "save_parsed", fail_after_save)
    CustomsImportWorker(imports).run_once()
    failed = imports.browse("admin").items[0]
    assert failed.status == "failed" and "private-data" not in failed.error
    assert imports.receipts.browse(CustomsReceiptQuery()).total == 0


def test_formatted_blank_tail_and_columns_are_ignored_but_real_late_data_is_rejected():
    book = Workbook()
    sheet = book.active
    sheet.append(HEADERS)
    sheet.append(row("REAL001", "01", "相纸", "张", 10))
    sheet.cell(150000, 100).fill = PatternFill("solid", fgColor="FFFFFF")
    buffer = io.BytesIO()
    book.save(buffer)
    result = parse("回执.xlsx", base64.b64encode(buffer.getvalue()).decode())
    assert result["rows"] == 1
    sheet.cell(150001, 1, "=1+1")
    buffer = io.BytesIO()
    book.save(buffer)
    with pytest.raises(ApiError, match="超过"):
        parse("回执.xlsx", base64.b64encode(buffer.getvalue()).decode())


def test_upload_api_accepts_over_128kb_as_pending_and_polls_with_identity(context, tmp_path):
    context.settings.customs_import_root = tmp_path / "uploads"
    app = create_app(context.settings, context.ns, context.engine)
    # 不启动 lifespan 消费者：验证 HTTP 202 只接收，不冒充已导入。
    client = TestClient(app)
    headers = {"Origin": context.settings.origin}
    assert (
        client.post(
            "/api/session",
            headers=headers,
            json={
                "username": "admin",
                "password": context.settings.admin_password,
            },
        ).status_code
        == 200
    )
    # 原表附带冗余工作簿元数据，超过旧 4MB；请求只接收，后台仍能解析真实明细。
    buffer = io.BytesIO(base64.b64decode(xlsx([row("REAL001", "01", "相纸", "张", 10)])))
    with ZipFile(buffer, "a") as archive:
        archive.writestr("customXml/padding.xml", b" " * (4 * 1024 * 1024))
    raw = buffer.getvalue()
    response = client.post(
        "/api/review/customs-receipts/import",
        headers=headers,
        json={
            "filename": "回执.xlsx",
            "content": base64.b64encode(raw).decode(),
        },
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "pending" and response.json()["result"] is None
    assert client.get("/api/review/customs-receipts/imports").json()["items"][0]["status"] == "pending"
    app.state.customs_import_worker.run_once()
    completed = client.get("/api/review/customs-receipts/imports").json()["items"][0]
    assert completed["status"] == "completed" and completed["result"]["rows"] == 1
    client.cookies.clear()
    assert client.get("/api/review/customs-receipts/imports").status_code == 401


def test_service_identity_cannot_enqueue(imports):
    with pytest.raises(ApiError, match="服务身份只读"):
        submit(imports, owner="service:test")


def test_all_pending_uploads_remain_visible_in_submission_order(imports):
    accepted = [submit(imports) for _ in range(32)]
    assert [job.id for job in imports.browse("admin").items] == [job.id for job in accepted]


def test_migration_refuses_to_delete_job_history(imports):
    from alembic import command
    from backend.manage import SCHEMA_INI, _config

    submit(imports)
    config = _config(SCHEMA_INI, imports.engine.url.render_as_string(hide_password=False))
    with pytest.raises(RuntimeError, match="已有数据"):
        command.downgrade(config, "0056_review_customs_difference_kinds")
    assert len(imports.browse("admin").items) == 1
