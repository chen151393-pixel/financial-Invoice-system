"""直接收汇资料：复用提单、合同、资料包，验证来源隔离、换版与金额不变。"""

import io
import zipfile

import pytest
from alembic import command
from backend.core.dependencies import current_owner
from backend.manage import SCHEMA_INI, _config
from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
from backend.modules.settlement.controller.document_controller import create_router
from backend.modules.settlement.dto.direct_document_dto import DirectDocumentQuery
from backend.modules.settlement.dto.ledger_dto import LedgerQuery
from backend.modules.settlement.dto.overview_dto import OverviewQuery
from backend.modules.settlement.entity.batch import settlement_batches
from backend.modules.settlement.service.direct_document_service import DirectDocumentService
from backend.modules.settlement.service.direct_document_source import DirectDocumentSource
from backend.modules.settlement.service.document_service import DocumentService
from backend.modules.settlement.service.ledger_service import LedgerService
from backend.modules.settlement.service.overview_service import OverviewService
from backend.tests.settlement.documents_support import SELLER, Documents, bill_pdf, encoded
from backend.tests.settlement.test_settlement_batches import create, services
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.settlement.test_settlement_ledger import add_receipt
from backend.tests.test_customs_receipts import _import, row
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import func, select


def direct_documents(engine, root):
    docs = Documents(engine, root)
    candidates, _ = services(engine)
    docs.views = DocumentService(engine, docs.reader, DirectDocumentSource(candidates))
    docs.bills.documents = docs.views
    docs.contracts.documents = docs.views
    docs.packages.documents = docs.views
    docs.list = DirectDocumentService(engine, candidates, docs.reader)
    return docs


def test_direct_document_lifecycle_keeps_money_and_detects_source_changes(seeded, tmp_path):
    docs = direct_documents(seeded, tmp_path)
    candidates, _ = services(seeded)
    add_receipt(seeded, "2026-11-10", "ACME LTD", "ACME LTD", "250")
    ledger = LedgerService(seeded, candidates)
    overview = OverviewService(seeded, candidates)
    before = (ledger.query(LedgerQuery()), overview.query(OverviewQuery()))
    with seeded.connect() as connection:
        count = connection.scalar(select(func.count()).select_from(settlement_batches))
    (item,) = docs.list.query(DirectDocumentQuery()).items
    assert (item.declarationNo, item.status, item.amount) == ("REAL872", "pending_bill", "1000.00")
    assert docs.list.query(DirectDocumentQuery(keyword="CD872")).total == 1
    assert docs.list.query(DirectDocumentQuery(keyword="YEX260827")).total == 1
    assert docs.list.query(DirectDocumentQuery(page=2, pageSize=1)).total == 1
    assert docs.list.query(DirectDocumentQuery(page=2, pageSize=1)).items == []
    assert docs.views.get("REAL872").batchId is None
    uploaded = docs.upload("REAL872").bills[0]
    assert uploaded.fileUrl == f"/api/settlement/direct-documents/REAL872/bills/{uploaded.id}/file"
    assert uploaded.declarationNos == ["REAL872"]
    docs.party("ACME LTD", "ACME LTD")
    seller = docs.party(SELLER, "DEMO EXPORT CO., LTD.")
    assert docs.list.query(DirectDocumentQuery(status="pending_contract")).total == 1
    generated = docs.generate("REAL872", seller.id)
    assert generated.complete and generated.package.allowed
    (contract,) = generated.contracts
    assert contract.amount == "1000.00" and not contract.stale
    filename, pdf = docs.contracts.file("REAL872", contract.id)
    assert filename.endswith(".pdf") and "1000.00" in PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "/direct-documents/REAL872/" in contract.fileUrl
    package_name, package = docs.packages.build("REAL872")
    assert "REAL872" in package_name
    assert any("销售合同" in name for name in zipfile.ZipFile(io.BytesIO(package)).namelist())
    assert docs.list.query(DirectDocumentQuery(status="complete")).total == 1
    assert (ledger.query(LedgerQuery()), overview.query(OverviewQuery())) == before
    with seeded.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(settlement_batches)) == count

    # 当前回执金额换版后沿用同一资料，但原合同失效；重生成读取新金额。
    _import(CustomsReceiptService(seeded), [row("REAL872", "01", "墨水", "个", 10, "ACME LTD", total=1200)])
    changed = docs.views.get("REAL872")
    assert changed.bills[0].id == uploaded.id and changed.contracts[0].stale
    assert not changed.package.allowed
    assert docs.list.query(DirectDocumentQuery(status="stale")).total == 1
    updated = docs.generate("REAL872", seller.id)
    assert updated.complete and updated.contracts[0].amount == "1200.00"
    docs.bills.remove("REAL872", uploaded.id, "finance-user")
    assert not docs.views.get("REAL872").complete


def test_direct_http_routes_and_files_are_scoped(seeded, tmp_path):
    docs = direct_documents(seeded, tmp_path)
    _, batches = services(seeded)
    hk = create(batches, ["REAL870"], "600")
    hk_docs = Documents(seeded, tmp_path)
    hk_bill = hk_docs.upload(hk.id).bills[0]
    app = FastAPI()
    from backend.core.middleware import register_error_handlers

    register_error_handlers(app)
    app.include_router(
        create_router(docs.views, docs.bills, docs.contracts, docs.packages, direct_list=docs.list)
    )
    app.dependency_overrides[current_owner] = lambda: "finance-user"
    client = TestClient(app)
    base = "/api/settlement/direct-documents/REAL872"
    assert client.post("/api/settlement/direct-documents/query", json={}).json()["total"] == 1
    assert client.get(base + "/documents").status_code == 200
    uploaded = client.post(
        base + "/bills", json={"fileName": "提单.pdf", "content": encoded(bill_pdf()), "declarationNos": []}
    )
    assert uploaded.status_code == 200, uploaded.text
    bill = uploaded.json()["bills"][0]
    assert client.get(bill["fileUrl"]).content.startswith(b"%PDF-")
    assert client.get(base + f"/bills/{hk_bill.id}/file").status_code == 404
    assert client.post(base + f"/bills/{hk_bill.id}/remove", json={}).status_code == 404
    assert client.get("/api/settlement/direct-documents/REAL870/documents").status_code == 409
    assert client.get("/api/settlement/direct-documents/UNKNOWN/documents").status_code == 404
    assert (
        client.post(
            base + "/bills",
            json={"fileName": "提单.pdf", "content": encoded(bill_pdf()), "declarationNos": ["REAL870"]},
        ).status_code
        == 409
    )  # 重复文件先拦截
    app.dependency_overrides[current_owner] = lambda: "service:robot"
    assert client.post(base + f"/bills/{bill['id']}/remove", json={}).status_code == 403
    assert hk_docs.views.get(hk.id).bills[0].id == hk_bill.id


def test_migration_preserves_hk_documents_and_refuses_lossy_downgrade(seeded, tmp_path):
    _, batches = services(seeded)
    hk = create(batches, ["REAL870"], "600")
    docs = Documents(seeded, tmp_path)
    bill = docs.upload(hk.id).bills[0]
    cfg = _config(SCHEMA_INI, seeded.url.render_as_string(hide_password=False))
    command.downgrade(cfg, "0049_settlement_direct_allocations")
    command.upgrade(cfg, "head")
    assert docs.views.get(hk.id).bills[0] == bill
    direct = direct_documents(seeded, tmp_path)
    direct.upload("REAL872")
    with pytest.raises(RuntimeError, match="已有直接收汇资料"):
        command.downgrade(cfg, "0049_settlement_direct_allocations")
