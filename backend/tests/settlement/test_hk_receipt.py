"""香港独立登记页：人工登记、严格对平、原件留存与幂等。"""

import io
from decimal import Decimal
from uuid import uuid4

import pytest
from backend.core.dependencies import current_owner
from backend.core.errors import ApiError
from backend.modules.settlement.controller.hk_receipt_controller import create_router
from backend.modules.settlement.dao import hk_slip_dao
from backend.modules.settlement.dto.hk_receipt_dto import (
    BankSlipUpload,
    HkRegistrationPreview,
    RegisterHkReceipt,
)
from backend.modules.settlement.entity.batch import settlement_batches
from backend.modules.settlement.service.bank_slip_file import content_of
from backend.modules.settlement.service.document_store import DocumentStore
from backend.modules.settlement.service.hk_receipt_service import HkReceiptService
from backend.tests.settlement.documents_support import bill_pdf, encoded
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.settlement.test_settlement_batches import services
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import func, select

LINES = (
    "BANK CREDIT ADVICE",
    "CREDIT AMOUNT: USD 600.00",
    "BANK CHARGES: USD 0.00",
    "VALUE DATE: 2026-11-18",
    "PAYER: TEST PAYER LTD",
    "REFERENCE: HSBC-REF-123",
)


def registration(engine, root):
    candidates, batches = services(engine)
    return HkReceiptService(engine, candidates, batches, DocumentStore(root), fee_alert=Decimal("50"))


def body(amount="600", fee="0", numbers=None, slip=False):
    return RegisterHkReceipt(
        requestId=uuid4(),
        declarationNos=numbers or ["REAL870"],
        receivedOn="2026-11-18",
        receivedAmount=amount,
        receivedFee=fee,
        payer="TEST PAYER",
        receivingAccount="测试香港账户",
        bankSlip=dict(fileName="water.pdf", content=encoded(bill_pdf(LINES))) if slip else None,
    )


def test_preview_strict_balance_date_and_nonblocking_fee_warning(seeded, tmp_path):
    service = registration(seeded, tmp_path)
    empty = service.preview(HkRegistrationPreview())
    assert not empty.submit.allowed and empty.rows == []
    under = service.preview(
        HkRegistrationPreview(declarationNos=["REAL870"], receivedAmount="500", receivedOn="2026-11-18")
    )
    assert under.difference == "100.00" and not under.submit.allowed
    ready = service.preview(
        HkRegistrationPreview(
            declarationNos=["REAL870"], receivedAmount="540", receivedFee="60", receivedOn="2026-11-18"
        )
    )
    assert ready.balanced and ready.submit.allowed
    assert next(c.state for c in ready.checks if c.key == "fee") == "warning"
    assert (
        service.preview(
            HkRegistrationPreview(declarationNos=["REAL870"], receivedAmount="600")
        ).submit.allowed
        is False
    )
    invalid = service.preview(
        HkRegistrationPreview(declarationNos=["REAL872"], receivedAmount="1000", receivedOn="2026-11-18")
    )
    assert not invalid.submit.allowed and "直接收汇" in invalid.submit.reason
    assert not service.preview(HkRegistrationPreview(declarationNos=["MISSING"])).submit.allowed


def test_register_attaches_proof_in_same_transaction_and_retry_is_idempotent(seeded, tmp_path):
    service = registration(seeded, tmp_path)
    request = body(slip=True)
    result = service.register(request, "finance-user")
    assert result.receivedSlipName == "water.pdf" and result.receivedSlipUrl.endswith(
        f"/{result.id}/bank-slip/file"
    )
    assert service.file(result.id)[1].startswith(b"%PDF-")
    assert service.register(request, "finance-user").id == result.id
    assert len(list(tmp_path.glob("*.pdf"))) == 1
    assert "测试香港账户" in service.preview(HkRegistrationPreview()).accounts
    with seeded.connect() as connection:
        slip = hk_slip_dao.get(connection, result.id)
        assert slip["uploaded_by"] == "finance-user"
        assert connection.scalar(select(func.count()).select_from(settlement_batches)) == 1
    service.store.path(slip["file_id"], "pdf").write_bytes(b"changed")
    with pytest.raises(ApiError, match="登记记录不一致"):
        service.file(result.id)


def test_rejected_registration_cleans_unattached_proof_and_changes_no_business_state(seeded, tmp_path):
    service = registration(seeded, tmp_path)
    with pytest.raises(ApiError, match="对平"):
        service.register(body(amount="500", slip=True), "finance-user")
    assert list(tmp_path.glob("*.pdf")) == []
    with seeded.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(settlement_batches)) == 0
    with pytest.raises(ApiError) as refused:
        service.register(body(), "service:test")
    assert refused.value.status == 403


def test_receipt_routes_manually_register_and_store_pdf(seeded, tmp_path):
    service = registration(seeded, tmp_path)
    app = FastAPI()
    app.dependency_overrides[current_owner] = lambda: "finance-user"
    app.include_router(create_router(service))
    with TestClient(app) as client:
        preview = client.post(
            "/api/settlement/hk-workbench/receipt-preview",
            json={"declarationNos": ["REAL870"], "receivedAmount": "600", "receivedOn": "2026-11-18"},
        )
        assert preview.status_code == 200 and preview.json()["submit"]["allowed"]
        result = client.post(
            "/api/settlement/hk-workbench/register", json=body(slip=True).model_dump(mode="json")
        )
        assert result.status_code == 200
        file = client.get(result.json()["receivedSlipUrl"])
        assert file.status_code == 200 and file.headers["content-type"] == "application/pdf"


def test_bank_slip_attachment_checks_pdf_without_extracting_fields():
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    stream = io.BytesIO()
    writer.write(stream)
    content = stream.getvalue()
    assert content_of(BankSlipUpload(fileName="scan.pdf", content=encoded(content))) == content
    with pytest.raises(ApiError, match="须为 PDF"):
        content_of(BankSlipUpload(fileName="not.pdf", content=encoded(b"not-pdf")))
    with pytest.raises(ApiError, match="无法读取"):
        content_of(BankSlipUpload(fileName="bad.pdf", content=encoded(b"%PDF- broken")))
