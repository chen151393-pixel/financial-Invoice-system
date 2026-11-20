"""报关单结汇详情：完整历史冲抵证据、真实资料范围、归档读取及只读接口。"""

from datetime import date
from decimal import Decimal

import pytest
from backend.core.dependencies import current_owner
from backend.core.errors import ApiError
from backend.modules.settlement.controller.receivable_controller import create_router
from backend.modules.settlement.dto.receivable_dto import ReceivableQuery
from backend.modules.settlement.policy import declaration_detail_policy as policy
from backend.modules.settlement.service.declaration_detail_service import DeclarationDetailService
from backend.modules.settlement.service.receivable_service import ReceivableService
from backend.tests.settlement.documents_support import Documents
from backend.tests.settlement.test_direct_documents import direct_documents
from backend.tests.settlement.test_settlement_batches import create, legacy_direct_batch, services
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.settlement.test_settlement_ledger import add_receipt
from backend.tests.settlement.test_settlement_receivables import bank, declaration
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import ns as ns
from fastapi import FastAPI
from fastapi.testclient import TestClient


def views(engine, reader):
    candidates, _ = services(engine)
    receivables = ReceivableService(engine, candidates, reader, today=lambda: date(2026, 11, 20))
    return receivables, DeclarationDetailService(receivables, fee_alert=Decimal("50"))


def test_fifo_evidence_shares_paid_results_and_keeps_payer():
    rows = [declaration("A", "500", "2026-10-01"), declaration("B", "300", "2026-11-01")]
    for row, paid in zip(rows, ["500", "100"], strict=True):
        row.update(
            route="direct", usable=True, received=Decimal(paid), outstanding=row["amount"] - Decimal(paid)
        )
    banks = [
        dict(
            bank("200"),
            id=1,
            receipt_date=date(2026, 10, 15),
            reference="FT1",
            payer_key="other",
            payer_name="Other Ltd",
        ),
        dict(
            bank("400"),
            id=2,
            receipt_date=date(2026, 11, 10),
            reference="FT2",
            payer_key="acme",
            payer_name="ACME LTD",
        ),
    ]
    # 使用真实规范化键，不能跨客户或收款抬头。
    for row in banks:
        row["customer_key"] = policy.rules.normalize_name("ACME LTD")
    banks += [
        dict(banks[0], id=3, receiving_company="其他公司", amount=Decimal("9000")),
        dict(banks[0], id=4, currency="EUR", amount=Decimal("9000")),
    ]
    evidence, balance = policy.direct_evidence(rows[1], rows, banks)
    assert balance == "200.00"
    assert [[r["appliedAmount"] for r in e["receipts"]] for e in evidence] == [
        ["200.00", "300.00"],
        ["100.00"],
    ]
    assert evidence[0]["receipts"][0]["thirdParty"] and evidence[0]["receipts"][0]["payer"] == "Other Ltd"
    assert evidence[1]["current"] and evidence[1]["outstandingAmount"] == "200.00"
    assert sum(Decimal(a["appliedAmount"]) for r in evidence for a in r["receipts"]) == Decimal("600")


def test_direct_detail_agrees_with_list_and_does_not_require_documents(seeded, tmp_path):
    docs = Documents(seeded, tmp_path)
    receivables, details = views(seeded, docs.reader)
    before = receivables.query(ReceivableQuery())
    company = next(row.exportCompany for row in before.items if row.declarationNo == "REAL872")
    add_receipt(seeded, "2026-11-12", "THIRD PARTY", "ACME LTD", "400", company=company, reference="FT-real")
    result = details.get("REAL872")
    listed = next(row for row in receivables.query(ReceivableQuery()).items if row.declarationNo == "REAL872")
    assert result.item == listed
    assert result.item.stage == "partial" and result.ledgerBalance == "600.00"
    assert result.batch is None and result.documents.scopeKind == "single"
    assert result.allocations[0].receipts[0].appliedAmount == "400.00"
    assert result.allocations[0].receipts[0].thirdParty
    add_receipt(seeded, "2026-11-13", "ACME LTD", "ACME LTD", "650", company=company)
    result = details.get("REAL872")
    assert result.item.stage == "settled" and result.ledgerBalance == "-50.00"
    assert result.steps[-1].state == "done" and result.documents.issues
    # 刷新详情不建立香港批次或生成资料。
    assert result.batch is None and not result.events
    assert details.get("REAL872") == result


def test_hk_detail_uses_batch_scope_and_current_declaration_documents(seeded, tmp_path):
    docs = Documents(seeded, tmp_path)
    _, batches = services(seeded)
    receivables, details = views(seeded, docs.reader)
    unregistered = details.get("REAL870")
    assert unregistered.documents.scopeKind == "none" and unregistered.batch is None
    batch = create(batches, ["REAL870", "REAL871"], "990.50", fee="10")
    docs.upload(batch.id, numbers=["REAL870"])
    one = details.get("REAL870")
    two = details.get("REAL871")
    assert one.batch.declaredTotal == "1000.50" and one.batch.receivedFee == "10.00"
    assert set(one.documents.scopeNumbers) == {"REAL870", "REAL871"}
    assert one.documents.bills and not two.documents.bills
    assert any(event.description.startswith("上传提单") for event in one.events)
    assert len(one.steps) == 5 and not one.allocations
    assert one.item == next(
        r for r in receivables.query(ReceivableQuery()).items if r.declarationNo == "REAL870"
    )


def test_direct_documents_are_read_only_and_legacy_batch_is_not_hk(seeded, tmp_path):
    docs = direct_documents(seeded, tmp_path)
    docs.upload("REAL872")
    _, details = views(seeded, docs.reader)
    result = details.get("REAL872")
    assert result.documents.bills[0].fileUrl.startswith("/api/settlement/direct-documents/REAL872/")
    assert result.documents.bills[0].declarationNos == ["REAL872"]
    legacy_direct_batch(seeded)
    legacy = details.get("REAL872")
    assert legacy.batch is None and legacy.documents.scopeKind == "single"
    assert len(legacy.steps) == 3


def test_detail_routes_and_archived_file_integrity(seeded, tmp_path, monkeypatch):
    docs = Documents(seeded, tmp_path)
    receivables, details = views(seeded, docs.reader)
    import hashlib

    original = tmp_path / "archive" / "REAL870.xls"
    original.write_bytes(b"archived-original")
    file = dict(
        filename="REAL870.xls", path=str(original), sha256=hashlib.sha256(original.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(
        docs.reader.declaration_files,
        "state",
        lambda c, items: [
            dict(
                declaration_no=i["declaration_no"],
                record_no="CD",
                status="archived",
                label="已归档",
                files=[file],
                note="",
            )
            for i in items
        ],
    )
    app = FastAPI()
    app.dependency_overrides[current_owner] = lambda: "tester"
    app.include_router(create_router(receivables, details))
    with TestClient(app) as client:
        body = client.get("/api/settlement/receivables/REAL870").json()
        assert body["documents"]["original"]["files"][0]["url"].endswith("REAL870/originals/0")
        response = client.get("/api/settlement/receivables/REAL870/originals/0")
        assert response.status_code == 200 and response.content == b"archived-original"
        assert "attachment" in response.headers["content-disposition"]
        assert client.get("/api/settlement/receivables/REAL870/originals/-1").status_code == 422
    original.write_bytes(b"changed")
    with pytest.raises(ApiError, match="归档记录不一致"):
        details.original("REAL870", 0)
    with pytest.raises(ApiError) as missing:
        details.get("NOT-FOUND")
    assert missing.value.status == 404
