"""共享盘保存规则使用临时目录验证，不写入真实共享盘。"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from backend.core.config import ROOT
from backend.core.database import make_engine
from backend.core.errors import ApiError
from backend.integrations.contract_archive import ContractArchive, contract_filename
from backend.manage import upgrade
from backend.modules.reconciliation import task_dao
from backend.modules.reconciliation import task_service as task_service_module
from backend.modules.reconciliation.task_entity import documents
from backend.tests.test_finance_list import OWNER
from backend.tests.test_invoice_tasks import local_source as local_source
from backend.tests.test_task_documents import PDF, ContractSource, task_service
from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError


def test_china_download_date_filename_and_same_content_reuse(tmp_path):
    archive = ContractArchive(tmp_path)
    at = datetime(2026, 8, 16, 16, 30, tzinfo=UTC).timestamp()
    path, name = archive.save("YE-HH20260422-X1004-1", "浙江洪皓工贸有限公司", at, PDF)
    assert name == "YE-HH20260422-X1004-1浙江洪皓工贸有限公司.pdf"
    target = Path(path)
    assert target.parent.name == "2026年8月17日"
    original = target.stat().st_mtime_ns
    assert archive.save("YE-HH20260422-X1004-1", "浙江洪皓工贸有限公司", at, PDF)[0] == path
    assert target.stat().st_mtime_ns == original
    archive.save("SECOND", "供应商", at + 60, PDF)
    assert len(list(tmp_path.iterdir())) == 1
    assert not list(tmp_path.rglob("*.tmp"))


def test_same_name_different_content_never_overwrites(tmp_path):
    archive = ContractArchive(tmp_path)
    path, _ = archive.save("SUB-1", "供应商", 0, PDF)
    with pytest.raises(ApiError) as error:
        archive.save("SUB-1", "供应商", 0, PDF + b"different")
    assert error.value.status == 409
    assert Path(path).read_bytes() == PDF


def test_missing_share_is_not_created_and_bad_filename_cannot_escape(tmp_path):
    root = tmp_path / "offline-share"
    with pytest.raises(ApiError) as error:
        ContractArchive(root).save("SUB-1", "供应商", 0, PDF)
    assert error.value.status == 503 and not root.exists()
    assert contract_filename("../SUB:1", "公司/部门*") == ".._SUB_1公司_部门_.pdf"
    with pytest.raises(ApiError):
        contract_filename("", "公司")


def test_share_failure_retry_redownloads_without_pdf_cache(context, local_source, tmp_path):
    contract = ContractSource()
    service, task, order = task_service(context, local_source, contract)
    service.archive = ContractArchive(tmp_path / "offline")
    with pytest.raises(ApiError) as error:
        service.prepare_document(task.id, order, OWNER)
    assert error.value.status == 503
    pending = service.detail(task.id, OWNER)
    assert pending.task.status == "documents_pending"
    assert pending.documents[0].status == "archive_pending"
    assert pending.documents[0].prepare.allowed
    with context.engine.connect() as connection:
        assert connection.execute(select(documents.c.content)).scalar_one() is None
    assert contract.calls == 1
    service.archive = ContractArchive(tmp_path)
    ready = service.prepare_document(task.id, order, OWNER)
    assert ready.task.status == "notify_pending" and ready.documents[0].archivedAt
    assert Path(ready.documents[0].archivePath).read_bytes() == PDF
    assert contract.calls == 2
    with context.engine.connect() as connection:
        assert connection.execute(select(documents.c.content)).scalar_one() is None


def test_retry_after_midnight_keeps_first_download_date(context, local_source, tmp_path, monkeypatch):
    contract = ContractSource()
    service, task, order = task_service(context, local_source, contract)
    at = int(datetime(2026, 8, 16, 16, 30, tzinfo=UTC).timestamp())
    monkeypatch.setattr(task_service_module, "time", SimpleNamespace(time=lambda: at))
    service.archive = ContractArchive(tmp_path / "offline")
    with pytest.raises(ApiError):
        service.prepare_document(task.id, order, OWNER)
    at += 86400
    service.archive = ContractArchive(tmp_path)
    ready = service.prepare_document(task.id, order, OWNER)
    assert Path(ready.documents[0].archivePath).parent.name == "2026年8月17日"
    assert not (tmp_path / "2026年8月18日").exists()


def test_retry_refuses_changed_pdf_and_unavailable_source(context, local_source, tmp_path, monkeypatch):
    contract = ContractSource()
    service, task, order = task_service(context, local_source, contract)
    service.archive = ContractArchive(tmp_path / "offline")
    with pytest.raises(ApiError):
        service.prepare_document(task.id, order, OWNER)
    service.archive = ContractArchive(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(contract, "unavailable_reason", lambda: "合同来源未配置")
        assert not service.detail(task.id, OWNER).documents[0].prepare.allowed
        with pytest.raises(ApiError) as error:
            service.prepare_document(task.id, order, OWNER)
        assert error.value.status == 503
    original = contract.download
    monkeypatch.setattr(contract, "download", lambda *args: {**original(*args), "content": PDF + b"changed"})
    with pytest.raises(ApiError) as error:
        service.prepare_document(task.id, order, OWNER)
    assert error.value.status == 409
    assert not list(tmp_path.rglob("*.pdf"))
    assert service.detail(task.id, OWNER).task.status == "documents_pending"
    with context.engine.connect() as connection:
        assert connection.execute(select(documents.c.content)).scalar_one() is None


def test_archive_record_failure_retry_reuses_file_without_cache(context, local_source, monkeypatch):
    contract = ContractSource()
    service, task, order = task_service(context, local_source, contract)

    def fail(*args):
        raise SQLAlchemyError("synthetic archive record failure")

    with monkeypatch.context() as patch:
        patch.setattr(task_dao, "archive_document", fail)
        with pytest.raises(ApiError) as error:
            service.prepare_document(task.id, order, OWNER)
        assert error.value.status == 503
    pending = service.detail(task.id, OWNER)
    assert pending.task.status == "documents_pending"
    with context.engine.connect() as connection:
        assert connection.execute(select(documents.c.content)).scalar_one() is None
    files = list(service.archive.root.rglob("*.pdf"))
    assert len(files) == 1
    original_time = files[0].stat().st_mtime_ns
    ready = service.prepare_document(task.id, order, OWNER)
    assert ready.task.status == "notify_pending"
    assert Path(ready.documents[0].archivePath) == files[0]
    assert files[0].stat().st_mtime_ns == original_time
    assert contract.calls == 2


def test_source_change_during_archive_does_not_advance(context, local_source, monkeypatch):
    from backend.modules.business.entity import load_tables

    service, task, order = task_service(context, local_source, ContractSource())
    original = service.archive.save

    def save_and_change(*args):
        result = original(*args)
        with local_source.engine.begin() as connection:
            lines = load_tables(connection)["purchase_order_lines"]
            connection.execute(lines.update().where(lines.c.id == 1).values(quantity="101"))
        return result

    monkeypatch.setattr(service.archive, "save", save_and_change)
    with pytest.raises(ApiError) as error:
        service.prepare_document(task.id, order, OWNER)
    assert error.value.status == 409
    detail = service.detail(task.id, OWNER)
    assert detail.task.status == "documents_pending"
    assert detail.sourceStatus == "changed"
    assert Path(detail.documents[0].archivePath).read_bytes() == PDF
    with context.engine.connect() as connection:
        assert connection.execute(select(documents.c.content)).scalar_one() is None


def test_metadata_migration_preserves_legacy_pdf_and_can_finish_archive(context, local_source, tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.sqlite'}"
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "0007_supplier_groups")
    engine = make_engine(url)
    try:
        legacy = SimpleNamespace(settings=replace(context.settings, database_url=url), engine=engine)
        contract = ContractSource()
        service, task, order = task_service(legacy, local_source, contract)
        with engine.begin() as connection:
            import hashlib

            task_dao.save_document(
                connection,
                {
                    "task_id": task.id,
                    "order_id": order,
                    "environment": "production",
                    "ns_id": "548",
                    "filename": "legacy.pdf",
                    "sha256": hashlib.sha256(PDF).hexdigest(),
                    "content": PDF,
                    "downloaded_at": 0,
                },
            )
        upgrade(url)
        assert next(
            column
            for column in inspect(engine).get_columns("finance_task_documents")
            if column["name"] == "content"
        )["nullable"]
        service.contract_source = None
        assert service.detail(task.id, OWNER).documents[0].prepare.allowed
        ready = service.prepare_document(task.id, order, OWNER)
        assert ready.task.status == "notify_pending"
        assert contract.calls == 0
        assert Path(ready.documents[0].archivePath).read_bytes() == PDF
        with engine.connect() as connection:
            row = connection.execute(select(documents)).mappings().one()
            assert row["content"] == PDF and row["sha256"] == hashlib.sha256(PDF).hexdigest()
    finally:
        engine.dispose()
